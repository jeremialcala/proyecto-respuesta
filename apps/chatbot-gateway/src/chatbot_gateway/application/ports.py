"""Puertos de la Pasarela de Chatbot. Los adaptadores (Ollama, SQS, Vault, Postgres) los implementan."""
from __future__ import annotations

from typing import Optional, Protocol, Sequence

from ..domain.conversation import ConversationContext, SessionProfile, Turn
from ..domain.models import ReportDraft


class BodyCipher(Protocol):
    """Descifra el cuerpo JWE de inbound.text (reverso del Meta Handler — ADR-0008)."""

    def decrypt(self, jwe_body: str) -> str: ...


class Embedder(Protocol):
    """Genera embeddings de texto (modelo on-prem, p. ej. nomic-embed-text vía Ollama).

    Devuelve `[]` si los embeddings están deshabilitados; en ese caso la memoria opera solo con la
    ventana reciente (sin recuperación semántica).
    """

    def embed(self, text: str) -> Sequence[float]: ...


class ConversationStore(Protocol):
    """Memoria de conversación por contacto (estado por interlocutor — ADR-0015).

    Persiste turnos y el perfil de sesión; recupera el contexto relevante para el turno actual.
    """

    def load(self, key: str, query_embedding: Sequence[float], *,
             recent_n: int, top_k: int) -> ConversationContext:
        """Carga perfil + últimos `recent_n` turnos + `top_k` turnos similares a la consulta."""
        ...

    def append_turn(self, key: str, turn: Turn, embedding: Sequence[float]) -> None:
        """Añade un turno (con su embedding, si lo hay) al historial del contacto."""
        ...

    def save_profile(self, key: str, profile: SessionProfile) -> None:
        """Persiste el perfil acumulado (borrador del reporte y datos del interlocutor)."""
        ...


class LlmClient(Protocol):
    """LLM on-premises (Ollama) — NO autoritativo: conversa y extrae, no decide estados (ADR-0001)."""

    def converse(self, user_text: str, context: ConversationContext
                 ) -> tuple[str, Optional[ReportDraft]]:
        """Devuelve (respuesta, borrador|None) usando el contexto de la conversación."""
        ...


class ReplyPublisher(Protocol):
    """Publica outbound.reply (lo entrega el servicio de salida por la Graph API)."""

    def publish_reply(self, envelope: dict) -> None: ...


class ReportPublisher(Protocol):
    """Publica report.received hacia el core-backend/intake (captura, no autoritativa)."""

    def publish_report(self, envelope: dict) -> None: ...


class NotificationPublisher(Protocol):
    """Publica notification.sent para auditar las notificaciones al reportante (ADR-0020 RF-22)."""

    def publish_notification(self, envelope: dict) -> None: ...


class EventLog(Protocol):
    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None: ...
