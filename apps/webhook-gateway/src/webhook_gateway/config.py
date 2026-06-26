"""Configuración del Webhook Gateway (12-factor). ADR-0005 (ingestión Meta) / ADR-0012 (SQS)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BotConfig:
    """Credenciales por bot de Meta. El JWT/verify_token y el app_secret se guardan en Postgres/Vault."""
    bot_id: str
    verify_token: str   # handshake GET (hub.verify_token)
    app_secret: str     # HMAC de X-Hub-Signature-256


@dataclass(frozen=True)
class GatewayConfig:
    aws_region: str = "sa-east-1"                 # ADR-0006
    raw_queue_url: str = ""                        # SQS: meta.received
    redis_url: str = "redis://localhost:6379/0"   # guarda de idempotencia
    idempotency_ttl_seconds: int = 86400          # TTL dedup (Meta reintenta) — afinar
    producer: str = "webhook-gateway"
    # MVP: WhatsApp. Se toleran otros object types pero el MVP procesa whatsapp_business_account.
    allowed_objects: tuple[str, ...] = ("whatsapp_business_account",)
    bots: dict[str, BotConfig] = field(default_factory=dict)

    @staticmethod
    def from_env() -> "GatewayConfig":
        # Bot único para el MVP, leído de entorno (en prod: catálogo en Postgres/Vault — ADR-0005/0008).
        bots: dict[str, BotConfig] = {}
        bot_id = os.getenv("META_BOT_ID", "")
        if bot_id:
            bots[bot_id] = BotConfig(
                bot_id=bot_id,
                verify_token=os.getenv("META_VERIFY_TOKEN", ""),
                app_secret=os.getenv("META_APP_SECRET", ""),
            )
        return GatewayConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            raw_queue_url=os.getenv("SQS_RAW_QUEUE_URL", ""),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            idempotency_ttl_seconds=int(os.getenv("IDEMPOTENCY_TTL", "86400")),
            bots=bots,
        )
