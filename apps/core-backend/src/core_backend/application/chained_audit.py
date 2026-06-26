"""Auditoría encadenada (ADR-0007): combina el hash de dominio con un AuditStore persistente.

Cada `record` toma el último hash + el siguiente `seq` del store, crea el `AuditEntry` (dominio) y lo
persiste. La integridad se verifica con `domain.audit.verify_chain` sobre las filas almacenadas.
"""
from __future__ import annotations

from ..domain.audit import AuditEntry, make_entry
from .ports import AuditStore


class ChainedAudit:
    def __init__(self, store: AuditStore) -> None:
        self._store = store

    def record(self, actor: str, action: str, payload: dict) -> AuditEntry:
        entry = make_entry(self._store.next_seq(), actor, action, payload, self._store.last_hash())
        self._store.append(entry)
        return entry
