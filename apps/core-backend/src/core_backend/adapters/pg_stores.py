"""Stores Postgres (reportes, entidades, auditoría append-only). `psycopg` perezoso. Esqueleto fase 03.

Esquema dinámico: el reporte guarda el núcleo + `attributes JSONB`. La auditoría es una tabla
INSERT-only con `seq`, `prev_hash`, `hash` (ADR-0007); las correcciones se hacen con filas nuevas.
"""
from __future__ import annotations

from typing import Optional

from ..domain.audit import AuditEntry, GENESIS
from ..domain.models import PersonState, Report

_DDL = """
CREATE TABLE IF NOT EXISTS reports (
  report_id text PRIMARY KEY, entity_id text NOT NULL,
  intention text NOT NULL, subject_name text NOT NULL,
  -- Documento OPCIONAL: la identidad del sistema es biométrica, no la cédula (ADR-0020). Quien reporta
  -- a un tercero rara vez tiene su documento; exigirlo rechazaba reportes válidos.
  id_type text, id_number text,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Idempotente: alinea tablas YA creadas con NOT NULL al nuevo esquema (CREATE IF NOT EXISTS no las altera).
ALTER TABLE reports ALTER COLUMN id_type DROP NOT NULL;
ALTER TABLE reports ALTER COLUMN id_number DROP NOT NULL;
CREATE TABLE IF NOT EXISTS entities (
  entity_id text PRIMARY KEY, state text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_log (
  seq bigint PRIMARY KEY, actor text NOT NULL, action text NOT NULL,
  payload jsonb NOT NULL, prev_hash text NOT NULL, hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


class PgStores:
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

    # ReportStore
    def save_report(self, report_id: str, entity_id: str, report: Report) -> None:
        import json
        self._c().execute(
            "INSERT INTO reports (report_id, entity_id, intention, subject_name, id_type, id_number, attributes)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (report_id, entity_id, report.intention, report.subject_name, report.id_type,
             report.id_number, json.dumps(report.attributes)))

    # EntityStore
    def create_entity(self, entity_id: str, state: PersonState) -> None:
        self._c().execute("INSERT INTO entities (entity_id, state) VALUES (%s,%s)"
                          " ON CONFLICT (entity_id) DO NOTHING", (entity_id, state.value))

    def get_state(self, entity_id: str) -> Optional[PersonState]:
        cur = self._c().execute("SELECT state FROM entities WHERE entity_id=%s", (entity_id,))
        row = cur.fetchone()
        return PersonState(row[0]) if row else None

    def set_state(self, entity_id: str, state: PersonState) -> None:
        self._c().execute("UPDATE entities SET state=%s, updated_at=now() WHERE entity_id=%s",
                          (state.value, entity_id))

    # AuditStore
    def last_hash(self) -> str:
        cur = self._c().execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else GENESIS

    def next_seq(self) -> int:
        cur = self._c().execute("SELECT COALESCE(MAX(seq),0)+1 FROM audit_log")
        return int(cur.fetchone()[0])

    def append(self, entry: AuditEntry) -> None:
        import json
        self._c().execute(
            "INSERT INTO audit_log (seq, actor, action, payload, prev_hash, hash)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (entry.seq, entry.actor, entry.action, json.dumps(entry.payload),
             entry.prev_hash, entry.hash))
