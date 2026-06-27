"""Configuración de la Pasarela de Chatbot (12-factor). ADR-0001 (LLM on-prem) / 0002 / 0012 / 0015."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatbotConfig:
    aws_region: str = "sa-east-1"
    input_queue_url: str = ""        # SQS: inbound.text (lo publica el Meta Handler)
    reply_queue_url: str = ""        # SQS: outbound.reply (lo consume el servicio de salida)
    report_queue_url: str = ""       # SQS: report.received (lo consume el core-backend/intake)
    entity_enrolled_queue_url: str = ""    # SQS: entity.enrolled (feedback "reporte completo", ADR-0016)
    enrollment_failed_queue_url: str = ""  # SQS: enrollment.failed (feedback de la foto, ADR-0016)
    ollama_url: str = "http://llm:11434"
    llm_model: str = "llama3.1:8b"   # modelo open cuantizado (ADR-0001), en la RTX 3090
    ollama_timeout: int = 120        # s; modelos grandes (27B) en frío superan 60s
    ollama_keep_alive: str = "30m"   # mantiene el modelo en VRAM entre mensajes (evita recargas)
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "chatbot-gateway"
    # --- memoria de conversación (ADR-0015) ---
    pgvector_dsn: str = ""           # Postgres+pgvector; vacío → store en memoria (dev/tests)
    embed_model: str = "nomic-embed-text"   # vacío → embeddings deshabilitados (solo ventana reciente)
    embed_dim: int = 768             # dimensión del modelo de embeddings (nomic-embed-text = 768)
    recent_turns: int = 6            # turnos textuales recientes que se pasan al LLM (coherencia)
    retrieval_k: int = 4             # turnos antiguos recuperados por similitud (economía de tokens)

    @staticmethod
    def from_env() -> "ChatbotConfig":
        return ChatbotConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            input_queue_url=os.getenv("SQS_INPUT_QUEUE_URL", ""),
            reply_queue_url=os.getenv("SQS_REPLY_QUEUE_URL", ""),
            report_queue_url=os.getenv("SQS_REPORT_QUEUE_URL", ""),
            entity_enrolled_queue_url=os.getenv("SQS_ENTITY_ENROLLED_URL", ""),
            enrollment_failed_queue_url=os.getenv("SQS_ENROLLMENT_FAILED_URL", ""),
            ollama_url=os.getenv("OLLAMA_URL", "http://llm:11434"),
            llm_model=os.getenv("LLM_MODEL", "llama3.1:8b"),
            ollama_timeout=int(os.getenv("OLLAMA_TIMEOUT", "120")),
            ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
            pgvector_dsn=os.getenv("PGVECTOR_DSN", ""),
            embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
            embed_dim=int(os.getenv("EMBED_DIM", "768")),
            recent_turns=int(os.getenv("CHAT_RECENT_TURNS", "6")),
            retrieval_k=int(os.getenv("CHAT_RETRIEVAL_K", "4")),
        )
