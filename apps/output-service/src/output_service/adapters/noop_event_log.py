"""EventLog no-op (MVP). Traza Event/EventAction en Postgres en fase 03 (ADR-0005)."""
from __future__ import annotations


class NoopEventLog:
    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None:
        return None
