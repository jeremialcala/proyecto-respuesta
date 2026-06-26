"""Configuración del Servicio de Salida (12-factor). ADR-0005 (salida) / 0012 (SQS)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputConfig:
    aws_region: str = "sa-east-1"
    input_queue_url: str = ""        # SQS: outbound.reply (lo publica el chatbot/notificador)
    graph_api_base: str = "https://graph.facebook.com/v20.0"
    redis_url: str = "redis://localhost:6379/0"
    hsm_template: str = "jornada_update"   # única plantilla HSM aprobada (MVP, componente 1)
    hsm_lang: str = "es"
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "output-service"

    @staticmethod
    def from_env() -> "OutputConfig":
        return OutputConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            input_queue_url=os.getenv("SQS_INPUT_QUEUE_URL", ""),
            graph_api_base=os.getenv("GRAPH_API_BASE", "https://graph.facebook.com/v20.0"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            hsm_template=os.getenv("HSM_TEMPLATE", "jornada_update"),
            hsm_lang=os.getenv("HSM_LANG", "es"),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
        )
