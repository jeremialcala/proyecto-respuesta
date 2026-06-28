"""AuditLog no-op (tests/dev). El real es `chained_audit_log` (cadena SHA-256 en Postgres, ADR-0007).

Guarda los registros en memoria para que los tests puedan inspeccionarlos.
"""
from __future__ import annotations


class NoopAuditLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def record(self, event: str, data: dict) -> None:
        self.records.append((event, data))
