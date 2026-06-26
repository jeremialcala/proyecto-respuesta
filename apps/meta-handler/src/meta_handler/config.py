"""Configuración del Meta Handler (12-factor). ADR-0005 (ingestión) / ADR-0012 (SQS)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class HandlerConfig:
    aws_region: str = "sa-east-1"                  # ADR-0006
    input_queue_url: str = ""                       # SQS: meta.received (lo publica el gateway)
    text_queue_url: str = ""                        # SQS: inbound.text  → LLM on-prem
    media_queue_url: str = ""                       # SQS: inbound.media → Worker de Bóveda
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "meta-handler"

    @staticmethod
    def from_env() -> "HandlerConfig":
        return HandlerConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            input_queue_url=os.getenv("SQS_INPUT_QUEUE_URL", ""),
            text_queue_url=os.getenv("SQS_TEXT_QUEUE_URL", ""),
            media_queue_url=os.getenv("SQS_MEDIA_QUEUE_URL", ""),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
        )
