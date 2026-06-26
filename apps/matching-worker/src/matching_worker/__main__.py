"""Punto de entrada del worker (wiring). AWS SQS/SNS + ArcFace + pgvector/FAISS (ADR-0012/0013)."""
from __future__ import annotations

from .application.matching_service import MatchingService
from .config import WorkerConfig
from .adapters.faiss_index import FaissAnnIndex
from .adapters.pgvector_store import PgvectorEmbeddingStore
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_sns_event_bus import SnsEventBus


def build_consumer(cfg: WorkerConfig) -> SqsConsumer:
    store = PgvectorEmbeddingStore(cfg.pgvector_dsn)
    index = FaissAnnIndex()              # d=512 por defecto (ADR-0013)
    index.rebuild_from(store)           # HNSW se reconstruye desde pgvector (fuente de verdad)
    bus = SnsEventBus(cfg.output_topic_arn, cfg.aws_region, producer=cfg.producer)
    service = MatchingService(index=index, bus=bus, top_k=cfg.top_k)
    return SqsConsumer(
        queue_url=cfg.input_queue_url,
        region=cfg.aws_region,
        service=service,
        max_messages=cfg.max_messages,
        wait_time_seconds=cfg.wait_time_seconds,
    )


def main() -> None:
    cfg = WorkerConfig.from_env()
    consumer = build_consumer(cfg)
    consumer.start()


if __name__ == "__main__":
    main()
