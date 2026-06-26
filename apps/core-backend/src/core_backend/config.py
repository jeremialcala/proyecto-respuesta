"""Configuración del Core Backend (12-factor). ADR-0007 (datos/auditoría) / 0011 / 0012."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CoreConfig:
    aws_region: str = "sa-east-1"
    report_received_queue_url: str = ""    # SQS: report.received (lo publica el chatbot/portal)
    report_ingested_topic_arn: str = ""    # SNS: report.ingested → matching
    state_changed_topic_arn: str = ""      # SNS: state.changed → notificación + auditoría
    pgvector_dsn: str = ""                  # Postgres (reportes, entidades, auditoría)
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "core-backend"

    @staticmethod
    def from_env() -> "CoreConfig":
        return CoreConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            report_received_queue_url=os.getenv("SQS_REPORT_RECEIVED_URL", ""),
            report_ingested_topic_arn=os.getenv("SNS_REPORT_INGESTED_ARN", ""),
            state_changed_topic_arn=os.getenv("SNS_STATE_CHANGED_ARN", ""),
            pgvector_dsn=os.getenv("PGVECTOR_DSN", ""),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
        )
