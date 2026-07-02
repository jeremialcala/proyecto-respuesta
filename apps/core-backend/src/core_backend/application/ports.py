"""Puertos del Core Backend. Los adaptadores (Postgres, SQS/SNS) los implementan."""
from __future__ import annotations

from typing import Optional, Protocol

from ..domain.audit import AuditEntry
from ..domain.models import PersonState, Report


class ReportStore(Protocol):
    def save_report(self, report_id: str, entity_id: str, report: Report) -> None: ...


class EntityStore(Protocol):
    def create_entity(self, entity_id: str, state: PersonState) -> None: ...
    def get_state(self, entity_id: str) -> Optional[PersonState]: ...
    def set_state(self, entity_id: str, state: PersonState) -> None: ...


class AuditStore(Protocol):
    """Persistencia append-only de la cadena. `last()` da el hash previo; `append` guarda la fila."""

    def last_hash(self) -> str: ...
    def next_seq(self) -> int: ...
    def append(self, entry: AuditEntry) -> None: ...


class EventPublisher(Protocol):
    def publish(self, topic: str, envelope: dict) -> None: ...


class ReplyPublisher(Protocol):
    """Publica outbound.reply (acuse al reportante, RF-16) en la cola que consume el servicio de salida."""

    def publish_reply(self, envelope: dict) -> None: ...


class MediaCorrelationStore(Protocol):
    """Correlaciona la foto del contacto con su reporte (ADR-0016). Maneja ambos órdenes de llegada.

    Guarda por `contact_ref`, con TTL, el último `media_ref` recibido y los ids del reporte ingerido.
    Así, llegue antes la foto o el reporte, el otro lado la encuentra y dispara el enrolamiento.
    """

    def remember_media(self, contact_ref: str, media_ref: str) -> None: ...
    def get_media(self, contact_ref: str) -> Optional[str]: ...
    def remember_report(self, contact_ref: str, report_id: str, entity_id: str,
                        reporter: Optional[dict] = None, summary: Optional[dict] = None) -> None: ...
    def get_report(self, contact_ref: str) -> Optional[dict]: ...
