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
    """Envía por la Graph API: texto, plantilla HSM, imagen por `link`, o interactivo (ADR componente 1)."""

    def send_text(self, bot_id: str, channel: str, contact_ref: str, text: str) -> None: ...
    def send_template(self, bot_id: str, channel: str, contact_ref: str,
                      template: str, lang: str) -> None: ...
    def send_image(self, bot_id: str, channel: str, contact_ref: str,
                   link: str, caption: str) -> None:
        """Imagen renderizada por Meta desde una URL firmada del media-gateway (ADR-0017)."""
        ...
    def send_buttons(self, bot_id: str, channel: str, contact_ref: str,
                     body: str, buttons: list[tuple[str, str]]) -> None:
        """Mensaje interactivo con reply buttons (≤3). `buttons` = [(id, title), …]."""
        ...
    def send_list(self, bot_id: str, channel: str, contact_ref: str,
                  body: str, button_label: str, rows: list[tuple[str, str]]) -> None:
        """Mensaje interactivo tipo lista (hasta 10 filas). `rows` = [(id, title), …]."""
        ...


class MediaGrantClient(Protocol):
    """Emite una concesión en el media-gateway (plano interno) y devuelve la URL firmada (ADR-0017)."""

    def issue_grant(self, media_ref: str, *, content_type: str, purpose: str, channel: str,
                    report_id: str | None) -> str: ...


class EventLog(Protocol):
    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None: ...
