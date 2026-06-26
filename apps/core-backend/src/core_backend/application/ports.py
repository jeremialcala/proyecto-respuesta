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
