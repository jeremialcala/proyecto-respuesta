"""Punto de entrada del worker (wiring). Enrolamiento biométrico + desambiguación (ADR-0016).

Consume dos colas hacia el `EnrollmentService`:
- `report.ingested`               → detecta rostros, enrola o pide desambiguación.
- `face.disambiguation.resolved`  → enrola el rostro elegido y purga el resto.
Más un job de purga periódico de `PendingEnrollment` vencidos (A04). AWS SQS/SNS + ArcFace +
pgvector/FAISS (ADR-0012/0013/0016). El `MatchingService` (resolución de "encontrados") se cableará
al re-matching disparado por `entity.enrolled` (pendiente en ADR-0016).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

from .application.enrollment_service import EnrollmentService
from .config import WorkerConfig
from .adapters.arcface_facemapper import ArcFaceMapper
from .adapters.faiss_index import FaissAnnIndex
from .adapters.http_grant_revoker import HttpGrantRevoker
from .adapters.pg_pending_enrollment_store import PgPendingEnrollmentStore
from .adapters.pgvector_store import PgvectorEmbeddingStore
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_sns_event_bus import SnsEventBus
from .adapters.vault_media_gateway import VaultMediaGateway

log = logging.getLogger(__name__)


def build_enrollment_service(cfg: WorkerConfig):
    """Construye el EnrollmentService y devuelve también el PendingStore (para el job de purga)."""
    store = PgvectorEmbeddingStore(cfg.pgvector_dsn)
    store.init_schema()
    index = FaissAnnIndex()
    index.rebuild_from(store)                 # HNSW se reconstruye desde pgvector (fuente de verdad)
    pending = PgPendingEnrollmentStore(cfg.pgvector_dsn)
    pending.init_schema()
    bus = SnsEventBus({
        "candidate.generated": cfg.output_topic_arn,
        "entity.enrolled": cfg.entity_enrolled_topic_arn,
        "enrollment.failed": cfg.enrollment_failed_topic_arn,
        "face.disambiguation.requested": cfg.disambiguation_requested_topic_arn,
    }, cfg.aws_region, producer=cfg.producer)
    face_mapper = ArcFaceMapper(cfg.arcface_model_root)
    media = VaultMediaGateway(cfg.aws_region, cfg.crops_bucket, sse=cfg.s3_sse)
    # Revoca las concesiones del media-gateway al purgar (ADR-0016 §6); sin URL configurada, se omite.
    revoker = HttpGrantRevoker(cfg.media_gateway_url) if cfg.media_gateway_url else None
    service = EnrollmentService(
        face_mapper=face_mapper, media=media, store=store, index=index,
        pending=pending, bus=bus, grant_revoker=revoker,
        pending_ttl_seconds=cfg.pending_ttl_seconds, crop_ttl_seconds=cfg.pending_ttl_seconds,
    )
    return service, pending


def build_consumers(cfg: WorkerConfig, service: EnrollmentService) -> list[SqsConsumer]:
    return [
        SqsConsumer(cfg.input_queue_url, cfg.aws_region, service.on_report_ingested,
                    cfg.max_messages, cfg.wait_time_seconds, name="report.ingested"),
        SqsConsumer(cfg.disambiguation_resolved_queue_url, cfg.aws_region,
                    service.on_disambiguation_resolved, cfg.max_messages, cfg.wait_time_seconds,
                    name="face.disambiguation.resolved"),
    ]


def _purge_loop(pending: PgPendingEnrollmentStore, interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            n = pending.purge_expired(now_iso)
            if n:
                log.info("purga: %d PendingEnrollment vencidos eliminados", n)
        except Exception:
            log.exception("job de purga falló")


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = WorkerConfig.from_env()
    service, pending = build_enrollment_service(cfg)
    consumers = build_consumers(cfg, service)

    threads = [threading.Thread(target=c.start, name=c._name, daemon=True) for c in consumers]
    for t in threads:
        t.start()
    threading.Thread(target=_purge_loop, args=(pending, cfg.purge_interval_seconds),
                     name="purge", daemon=True).start()
    log.info("matching-worker arriba: enrolamiento + desambiguación (ADR-0016)")
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
