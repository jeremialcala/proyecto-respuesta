"""Puertos de la Pasarela de Chatbot. Los adaptadores (Ollama, SQS, Vault) los implementan."""
from __future__ import annotations

from typing import Optional, Protocol

from ..domain.models import ReportDraft


class BodyCipher(Protocol):
    """Descifra el cuerpo JWE de inbound.text (reverso del Meta Handler — ADR-0008)."""

    def decrypt(self, jwe_body: str) -> str: ...


class LlmClient(Protocol):
    """LLM on-premises (Ollama) — NO autoritativo: conversa y extrae, no decide estados (ADR-0001)."""

    def converse(self, user_text: str) -> tuple[str, Optional[ReportDraft]]:
        """Devuelve (respuesta_al_usuario, borrador_de_reporte | None)."""
        ...


class ReplyPublisher(Protocol):
    """Publica outbound.reply (lo entrega el servicio de salida por la Graph API)."""

    def publish_reply(self, envelope: dict) -> None: ...


class ReportPublisher(Protocol):
    """Publica report.received hacia el core-backend/intake (captura, no autoritativa)."""

    def publish_report(self, envelope: dict) -> None: ...


class EventLog(Protocol):
    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None: ...
