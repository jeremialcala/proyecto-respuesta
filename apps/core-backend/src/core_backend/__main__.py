"""Arranque de los consumidores del core (workers). La API REST se sirve con uvicorn (ver Dockerfile).

Dos colas hacia el IntakeService:
- `report.received` → persiste el reporte y emite `report.ingested` (con media_ref si ya hay foto).
- `media.stored`   → correlaciona la foto con el reporte del contacto y dispara el enrolamiento
                     re-emitiendo `report.ingested` con el media_ref (ADR-0016).
"""
from __future__ import annotations

import logging
import os
import threading

from .application.chained_audit import ChainedAudit
from .application.intake_service import IntakeService
from .adapters.pg_stores import PgStores
from .adapters.redis_correlation_store import RedisCorrelationStore
from .adapters.sns_publisher import SnsPublisher
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_reply_publisher import SqsReplyPublisher
from .config import CoreConfig

log = logging.getLogger(__name__)


def build_intake(cfg: CoreConfig) -> IntakeService:
    stores = PgStores(cfg.pgvector_dsn)
    stores.init_schema()   # idempotente (CREATE TABLE IF NOT EXISTS); el consumidor no dependía de la API
    publisher = SnsPublisher({"report.ingested": cfg.report_ingested_topic_arn,
                              "state.changed": cfg.state_changed_topic_arn,
                              "notification.sent": cfg.notification_sent_topic_arn}, cfg.aws_region)
    correlation = RedisCorrelationStore(cfg.redis_url, cfg.correlation_ttl_seconds)
    reply_pub = SqsReplyPublisher(cfg.outbound_reply_queue_url, cfg.aws_region)  # acuse RF-16
    return IntakeService(cfg, stores, stores, ChainedAudit(stores), publisher, correlation,
                         reply_pub=reply_pub)


def build_consumers(cfg: CoreConfig, intake: IntakeService) -> list[SqsConsumer]:
    consumers = [
        SqsConsumer(cfg.report_received_queue_url, cfg.aws_region, intake.handle,
                    cfg.max_messages, cfg.wait_time_seconds, name="report.received"),
    ]
    if cfg.media_stored_queue_url:
        consumers.append(
            SqsConsumer(cfg.media_stored_queue_url, cfg.aws_region, intake.on_media_stored,
                        cfg.max_messages, cfg.wait_time_seconds, name="media.stored"))
    return consumers


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = CoreConfig.from_env()
    intake = build_intake(cfg)
    consumers = build_consumers(cfg, intake)
    threads = [threading.Thread(target=c.start, name=c._name, daemon=True) for c in consumers]
    for t in threads:
        t.start()
    log.info("core-backend consumidores arriba: %s", ", ".join(c._name for c in consumers))
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
