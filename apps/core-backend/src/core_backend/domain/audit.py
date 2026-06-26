"""Auditoría append-only con encadenamiento SHA-256 (ADR-0007). Puro (stdlib).

Cada registro encadena `SHA-256(payload_canónico || hash_anterior)`. Alterar o borrar un registro
rompe la cadena y es detectable (`verify_chain`). No es un ledger distribuido; da no repudio
verificable bajo el operador (Modelo A).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, payload: dict) -> str:
    """Hash encadenado de un registro a partir del hash previo y el payload canónico."""
    data = (_canonical(payload) + "||" + (prev_hash or GENESIS)).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    actor: str
    action: str
    payload: dict
    prev_hash: str
    hash: str


def make_entry(seq: int, actor: str, action: str, payload: dict, prev_hash: str) -> AuditEntry:
    body = {"seq": seq, "actor": actor, "action": action, "payload": payload}
    return AuditEntry(seq=seq, actor=actor, action=action, payload=payload,
                      prev_hash=prev_hash or GENESIS, hash=compute_hash(prev_hash, body))


def verify_chain(entries: list[AuditEntry]) -> bool:
    """True si la cadena es íntegra (cada hash deriva del anterior y del payload)."""
    prev = GENESIS
    for e in entries:
        body = {"seq": e.seq, "actor": e.actor, "action": e.action, "payload": e.payload}
        if e.prev_hash != prev or e.hash != compute_hash(prev, body):
            return False
        prev = e.hash
    return True
