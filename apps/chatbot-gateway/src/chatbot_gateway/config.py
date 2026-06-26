"""Configuración de la Pasarela de Chatbot (12-factor). ADR-0001 (LLM on-prem) / 0002 / 0012."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatbotConfig:
    aws_region: str = "sa-east-1"
    input_queue_url: str = ""        # SQS: inbound.text (lo publica el Meta Handler)
    reply_queue_url: str = ""        # SQS: outbound.reply (lo consume el servicio de salida)
    report_queue_url: str = ""       # SQS: report.received (lo consume el core-backend/intake)
    ollama_url: str = "http://llm:11434"
    llm_model: str = "llama3.1:8b"   # modelo open cuantizado (ADR-0001), en la RTX 3090
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "chatbot-gateway"

    @staticmethod
    def from_env() -> "ChatbotConfig":
        return ChatbotConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            input_queue_url=os.getenv("SQS_INPUT_QUEUE_URL", ""),
            reply_queue_url=os.getenv("SQS_REPLY_QUEUE_URL", ""),
            report_queue_url=os.getenv("SQS_REPORT_QUEUE_URL", ""),
            ollama_url=os.getenv("OLLAMA_URL", "http://llm:11434"),
            llm_model=os.getenv("LLM_MODEL", "llama3.1:8b"),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
        )
