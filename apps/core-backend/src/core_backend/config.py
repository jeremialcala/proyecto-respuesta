"""Configuración del Core Backend (12-factor). ADR-0007 (datos/auditoría) / 0011 / 0012."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CoreConfig:
    aws_region: str = "sa-east-1"
    report_received_queue_url: str = ""    # SQS: report.received (lo publica el chatbot/portal)
    media_stored_queue_url: str = ""       # SQS: media.stored (correlación foto↔reporte, ADR-0016)
    report_ingested_topic_arn: str = ""    # SNS: report.ingested → matching/enrolamiento
    state_changed_topic_arn: str = ""      # SNS: state.changed → notificación + auditoría
    notification_sent_topic_arn: str = ""  # SNS: notification.sent (auditoría del acuse, ADR-0020 RF-22)
    outbound_reply_queue_url: str = ""     # SQS: outbound.reply (acuse al reportante, ADR-0020 RF-16)
    pgvector_dsn: str = ""                  # Postgres (reportes, entidades, auditoría)
    redis_url: str = "redis://localhost:6379/0"   # correlación foto↔reporte por contacto
    correlation_ttl_seconds: int = 86400          # ventana para vincular foto y reporte (ADR-0015)
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "core-backend"

    @staticmethod
    def from_env() -> "CoreConfig":
        return CoreConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            report_received_queue_url=os.getenv("SQS_REPORT_RECEIVED_URL", ""),
            media_stored_queue_url=os.getenv("SQS_MEDIA_STORED_URL", ""),
            report_ingested_topic_arn=os.getenv("SNS_REPORT_INGESTED_ARN", ""),
            state_changed_topic_arn=os.getenv("SNS_STATE_CHANGED_ARN", ""),
            notification_sent_topic_arn=os.getenv("SNS_NOTIFICATION_SENT_ARN", ""),
            outbound_reply_queue_url=os.getenv("SQS_OUTBOUND_REPLY_URL", ""),
            pgvector_dsn=os.getenv("PGVECTOR_DSN", ""),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            correlation_ttl_seconds=int(os.getenv("CORRELATION_TTL_SECONDS", "86400")),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
        )
