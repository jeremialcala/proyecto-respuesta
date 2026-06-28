"""Auditoría encadenada SHA-256 sobre Postgres (ADR-0007). Implementa el puerto `AuditLog`.

Cada `record` toma el último hash + el siguiente `seq`, encadena `SHA-256(payload_canónico ||
hash_anterior)` y lo persiste en una tabla INSERT-only. Alterar/borrar una fila rompe la cadena y es
detectable. Mismo esquema que el `audit_log` del core-backend. `psycopg` perezoso. Esqueleto fase 03.
"""
from __future__ import annotations

import hashlib
import json

_ACTOR = "media-gateway"
_GENESIS = "0" * 64

_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
  seq bigint PRIMARY KEY, actor text NOT NULL, action text NOT NULL,
  payload jsonb NOT NULL, prev_hash text NOT NULL, hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_hash(prev_hash: str, body: dict) -> str:
    data = (_canonical(body) + "||" + (prev_hash or _GENESIS)).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class ChainedAuditLog:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    def _c(self):
        if self._conn is None:
            import psycopg
            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def init_schema(self) -> None:
        self._c().execute(_DDL)

    def record(self, event: str, data: dict) -> None:
        conn = self._c()
        prev = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = prev[0] if prev else _GENESIS
        seq = int(conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM audit_log").fetchone()[0])
        body = {"seq": seq, "actor": _ACTOR, "action": event, "payload": data}
        h = _compute_hash(prev_hash, body)
        conn.execute(
            "INSERT INTO audit_log (seq, actor, action, payload, prev_hash, hash)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (seq, _ACTOR, event, json.dumps(data), prev_hash, h))
