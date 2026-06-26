"""Caso de uso del Gateway: verificar handshake, validar firma, deduplicar y publicar el crudo.

Convención del proyecto (ADR-0005): **el webhook no procesa ni toca workers**; su única salida es
publicar el payload crudo a `meta.received`. ACK 200 inmediato (Meta reintenta si no). Puro respecto
a infraestructura: depende solo de los puertos y del dominio.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..config import GatewayConfig
from ..domain import meta_payload, signature
from .events import build_envelope
from .ports import IdempotencyStore, RawPublisher


class Decision(Enum):
    ACCEPTED = "accepted"                 # publicado a meta.received (ACK 200)
    DUPLICATE = "duplicate"               # ya visto; se descarta (ACK 200)
    REJECTED_SIGNATURE = "rejected_sig"   # firma inválida (HTTP 403)
    REJECTED_UNKNOWN_BOT = "unknown_bot"  # bot no configurado (HTTP 403)
    REJECTED_OBJECT = "rejected_object"   # object no soportado (ACK 200, no se publica)


@dataclass(frozen=True)
class IngestResult:
    decision: Decision
    event_id: Optional[str] = None

    @property
    def http_status(self) -> int:
        # ACK rápido salvo fallo de autenticidad → 403 (Meta no debe reintentar un atacante).
        return 403 if self.decision in (
            Decision.REJECTED_SIGNATURE, Decision.REJECTED_UNKNOWN_BOT) else 200


class IngestService:
    def __init__(self, cfg: GatewayConfig, idem: IdempotencyStore, publisher: RawPublisher) -> None:
        self._cfg = cfg
        self._idem = idem
        self._pub = publisher

    # --- GET handshake (suscripción del webhook) ---
    def verify_subscription(self, bot_id: str, mode: str, token: str, challenge: str) -> Optional[str]:
        """Devuelve el challenge si el verify_token coincide; None si no (→ 403)."""
        bot = self._cfg.bots.get(bot_id)
        if bot and mode == "subscribe" and token and token == bot.verify_token:
            return challenge
        return None

    # --- POST de mensajes ---
    def ingest(self, bot_id: str, raw_body: bytes, raw_json: dict, signature_header: Optional[str]) -> IngestResult:
        bot = self._cfg.bots.get(bot_id)
        if bot is None:
            return IngestResult(Decision.REJECTED_UNKNOWN_BOT)

        if not signature.verify_signature(bot.app_secret, raw_body, signature_header):
            return IngestResult(Decision.REJECTED_SIGNATURE)

        summary = meta_payload.summarize(raw_json)
        if summary.object_type not in self._cfg.allowed_objects:
            return IngestResult(Decision.REJECTED_OBJECT)

        # Idempotencia: si el primer message_id ya se vio, es un reintento de Meta.
        key = summary.dedup_key
        if key is not None and self._idem.seen(f"{bot_id}:{key}"):
            return IngestResult(Decision.DUPLICATE)

        envelope = build_envelope(
            "meta.received",
            {"bot_id": bot_id, "object": summary.object_type, "raw": raw_json},
            self._cfg.producer,
        )
        self._pub.publish_raw(envelope)
        return IngestResult(Decision.ACCEPTED, event_id=envelope["event_id"])
