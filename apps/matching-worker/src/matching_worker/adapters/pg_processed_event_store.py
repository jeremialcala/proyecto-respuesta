"""ProcessedEventStore sobre Postgres (ADR-0018). `psycopg` perezoso, autocommit.

Ledger de `event_id` ya procesados para idempotencia ante redelivery de SQS (at-least-once, ADR-0012).
`mark_processed` se llama **tras** procesar con éxito; `already_processed` descarta la reentrega. La
clave primaria sobre `event_id` hace que el registro sea naturalmente idempotente. `purge_older_than`
acota el crecimiento de la tabla (corre en el job de purga periódico, igual que los pendientes).
"""
from __future__ import annotations

_DDL = """
CREATE TABLE IF NOT EXISTS processed_event (
    event_id     text PRIMARY KEY,
    processed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS processed_event_at_idx ON processed_event(processed_at);
"""


class PgProcessedEventStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    def _ensure(self):
        if self._conn is None:
            import psycopg
            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def init_schema(self) -> None:
        self._ensure().execute(_DDL)

    def already_processed(self, event_id: str) -> bool:
        cur = self._ensure().execute(
            "SELECT 1 FROM processed_event WHERE event_id = %s", (event_id,))
        return cur.fetchone() is not None

    def mark_processed(self, event_id: str) -> None:
        self._ensure().execute(
            "INSERT INTO processed_event (event_id) VALUES (%s) ON CONFLICT (event_id) DO NOTHING",
            (event_id,))

    def purge_older_than(self, iso: str) -> int:
        cur = self._ensure().execute(
            "DELETE FROM processed_event WHERE processed_at < %s", (iso,))
        return cur.rowcount
