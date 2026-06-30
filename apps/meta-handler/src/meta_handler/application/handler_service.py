"""Caso de uso del Meta Handler (ADR-0005): normaliza el crudo y reparte por tipo.

Consume el sobre `meta.received` (publicado por el Webhook Gateway), normaliza cada mensaje y publica:
- **texto / ubicación** → `inbound.text` con el cuerpo **cifrado en JWE** (al LLM on-prem).
- **imagen** → `inbound.media` con `media_id` + `mime` (el binario **no** viaja; lo baja la Bóveda).
Tipos no soportados y canales fuera del MVP se registran y se descartan. Idempotencia por `event_id`
del sobre aguas arriba; aquí se correlaciona por `message_id`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import HandlerConfig
from ..domain.models import Channel, MessageType, NormalizedMessage
from ..domain.normalize import normalize
from .events import build_envelope
from .ports import BodyCipher, EventLog, InboundPublisher, WindowStore


@dataclass(frozen=True)
class DispatchResult:
    text: int = 0
    media: int = 0
    skipped: int = 0


class _NoopWindowStore:
    """Default sin Redis (p. ej. tests): no abre ninguna ventana."""

    def mark(self, contact_ref: str) -> None:  # noqa: D401
        return None


class HandlerService:
    def __init__(self, cfg: HandlerConfig, publisher: InboundPublisher,
                 cipher: BodyCipher, event_log: EventLog,
                 window: WindowStore | None = None) -> None:
        self._cfg = cfg
        self._pub = publisher
        self._cipher = cipher
        self._log = event_log
        self._window = window or _NoopWindowStore()

    def handle(self, meta_received_envelope: dict) -> DispatchResult:
        payload = meta_received_envelope.get("payload", {}) or {}
        event_id = meta_received_envelope.get("event_id", "")
        bot_id = payload.get("bot_id", "")
        raw = payload.get("raw", {}) or {}

        text = media = skipped = 0
        for msg in normalize(raw):
            if msg.channel is not Channel.WHATSAPP:   # MVP: solo WhatsApp
                self._log.record_action(event_id, "normalize", "SKIP", f"canal {msg.channel.value}")
                skipped += 1
                continue
            # El usuario escribió → abre la ventana de 24h (habilita texto libre en la respuesta).
            self._window.mark(msg.contact_ref)
            if msg.type is MessageType.IMAGE:
                self._pub.publish_media(self._media_envelope(bot_id, msg))
                self._log.record_action(event_id, "dispatch_media", "OK", msg.message_id)
                media += 1
                if (msg.text or "").strip():   # imagen con PIE DE FOTO: el caption ES el reporte → también como texto
                    self._pub.publish_text(self._text_envelope(bot_id, msg))
                    self._log.record_action(event_id, "dispatch_text", "OK", msg.message_id + ":caption")
                    text += 1
            elif msg.type in (MessageType.TEXT, MessageType.LOCATION):
                self._pub.publish_text(self._text_envelope(bot_id, msg))
                self._log.record_action(event_id, "dispatch_text", "OK", msg.message_id)
                text += 1
            else:
                self._log.record_action(event_id, "dispatch", "SKIP", f"tipo {msg.type.value}")
                skipped += 1
        return DispatchResult(text=text, media=media, skipped=skipped)

    # --- construcción de eventos ---
    def _text_envelope(self, bot_id: str, msg: NormalizedMessage) -> dict:
        if msg.type is MessageType.LOCATION and msg.location is not None:
            body = {"kind": "location", "location": {
                "latitude": msg.location.latitude, "longitude": msg.location.longitude,
                "address": msg.location.address}}
        else:
            body = {"kind": "text", "text": msg.text or ""}
        return build_envelope("inbound.text", {
            "bot_id": bot_id,
            "channel": msg.channel.value,
            "contact_ref": msg.contact_ref,
            "message_id": msg.message_id,
            "jwe_body": self._cipher.encrypt(json.dumps(body, ensure_ascii=False)),
        }, self._cfg.producer)

    def _media_envelope(self, bot_id: str, msg: NormalizedMessage) -> dict:
        # El binario NO viaja: solo el media_id para que la Bóveda lo descargue (ADR-0005).
        return build_envelope("inbound.media", {
            "bot_id": bot_id,
            "channel": msg.channel.value,
            "contact_ref": msg.contact_ref,
            "message_id": msg.message_id,
            "media_id": msg.media_id,
            "media_type": "image",
            "mime_type": msg.mime_type,
        }, self._cfg.producer)
