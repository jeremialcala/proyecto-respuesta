"""Stores en memoria (para dev/tests y arranque sin Postgres). No persisten entre reinicios."""
from __future__ import annotations

from typing import Optional

from ..domain.audit import AuditEntry, GENESIS
from ..domain.models import PersonState, Report


class MemoryStores:
    def __init__(self) -> None:
        self.reports: dict = {}
        self.entities: dict = {}
        self.audit: list[AuditEntry] = []

    def save_report(self, report_id, entity_id, report: Report) -> None:
        self.reports[report_id] = (entity_id, report)

    def create_entity(self, entity_id, state: PersonState) -> None:
        self.entities.setdefault(entity_id, state)

    def get_state(self, entity_id) -> Optional[PersonState]:
        return self.entities.get(entity_id)

    def set_state(self, entity_id, state: PersonState) -> None:
        self.entities[entity_id] = state

    def last_hash(self) -> str:
        return self.audit[-1].hash if self.audit else GENESIS

    def next_seq(self) -> int:
        return len(self.audit) + 1

    def append(self, entry: AuditEntry) -> None:
        self.audit.append(entry)
