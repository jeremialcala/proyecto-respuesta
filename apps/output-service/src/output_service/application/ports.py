"""Puertos del Servicio de Salida. Los adaptadores (Graph, SQS, Redis, Vault) los implementan."""
from __future__ import annotations

from typing import Protocol


class BodyCipher(Protocol):
    """Descifra el cuerpo de outbound.reply (reverso del placeholder del chatbot — ADR-0008)."""

    def decrypt(self, jwe_body: str) -> str: ...


class WindowStore(Protocol):
    """¿La ventana de servicio de 24h está abierta para este contacto? (Redis, por message_id entrante)."""

    def is_open(self, contact_ref: str) -> bool: ...


class MetaSender(Protocol):
    """Envía por la Graph API: texto libre o plantilla HSM (ADR componente 1)."""

    def send_text(self, bot_id: str, channel: str, contact_ref: str, text: str) -> None: ...
    def send_template(self, bot_id: str, channel: str, contact_ref: str,
                      template: str, lang: str) -> None: ...


class EventLog(Protocol):
    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None: ...
