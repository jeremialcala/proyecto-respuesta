"""EventLog no-op para el MVP. La traza Event/EventAction en Postgres llega en fase 03 (ADR-0005)."""
from __future__ import annotations


class NoopEventLog:
    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None:
        return None
