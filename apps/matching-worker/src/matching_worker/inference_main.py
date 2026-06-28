"""Entrypoint del PLANO DE INFERENCIA (ADR-0019). Imagen OCI distinta de la del worker de control.

Stateless: consume `face.extract.requested`, corre ArcFace y publica `face.embedded` (solo vectores).
No toca Postgres, ni Vault, ni S3 — la galería/índice/desambiguación viven en el worker in-region. Pensado
para GPU dedicada (ADR-0018), incluido un nodo de burst on-demand verificado (vast.ai Secure Cloud) que
devuelve el vector y descarta la imagen al destruir la instancia.

`CMD ["python3","-m","matching_worker.inference_main"]` (ver `Dockerfile.inference`).
"""
from __future__ import annotations

import logging
import os

from .adapters.arcface_facemapper import ArcFaceMapper
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_sns_event_bus import SnsEventBus
from .application.inference_service import InferenceService
from .config import InferenceConfig

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = InferenceConfig.from_env()
    mapper = ArcFaceMapper(cfg.arcface_model_root)
    bus = SnsEventBus({"face.embedded": cfg.face_embedded_topic_arn}, cfg.aws_region,
                      producer=cfg.producer)
    service = InferenceService(mapper, bus)
    consumer = SqsConsumer(cfg.extract_queue_url, cfg.aws_region, service.on_extract_requested,
                           cfg.max_messages, cfg.wait_time_seconds, name="face.extract.requested")
    log.info("inference-worker arriba: extracción de embeddings ArcFace (ADR-0019, stateless)")
    consumer.start()


if __name__ == "__main__":
    main()
