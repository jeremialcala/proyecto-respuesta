"""Arranque del consumidor report.received (worker). La API REST se sirve con uvicorn (ver Dockerfile)."""
from __future__ import annotations

from .application.chained_audit import ChainedAudit
from .application.intake_service import IntakeService
from .adapters.pg_stores import PgStores
from .adapters.sns_publisher import SnsPublisher
from .adapters.sqs_consumer import SqsConsumer
from .config import CoreConfig


def build_consumer(cfg: CoreConfig) -> SqsConsumer:
    stores = PgStores(cfg.pgvector_dsn)
    publisher = SnsPublisher({"report.ingested": cfg.report_ingested_topic_arn,
                              "state.changed": cfg.state_changed_topic_arn}, cfg.aws_region)
    intake = IntakeService(cfg, stores, stores, ChainedAudit(stores), publisher)
    return SqsConsumer(cfg.report_received_queue_url, cfg.aws_region, intake,
                       cfg.max_messages, cfg.wait_time_seconds)


def main() -> None:
    build_consumer(CoreConfig.from_env()).start()


if __name__ == "__main__":
    main()
