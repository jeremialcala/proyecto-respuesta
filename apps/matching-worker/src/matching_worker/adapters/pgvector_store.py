"""Adaptador pgvector: fuente de verdad de embeddings (durable, borrado GDPR), **vector(512)**.

ArcFace/IResNet100 = 512-d (ADR-0013). Borrado real para el cierre de emergencia (ADR-0007). El
campo de embedding se versiona por modelo. `psycopg` se importa de forma perezosa. Afinado: fase 03.
"""
from __future__ import annotations

from typing import Sequence

from ..config import EMBEDDING_DIM

_DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS embeddings (
    id           bigserial PRIMARY KEY,
    entity_id    text NOT NULL,
    vector       vector({EMBEDDING_DIM}) NOT NULL,
    model        text NOT NULL DEFAULT 'arcface',
    model_version text NOT NULL DEFAULT 'iresnet100',
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS embeddings_entity_idx ON embeddings(entity_id);
"""


class PgvectorEmbeddingStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    def _ensure_conn(self):
        if self._conn is None:
            import psycopg
            from pgvector.psycopg import register_vector
            conn = psycopg.connect(self._dsn, autocommit=True)
            register_vector(conn)
            self._conn = conn
        return self._conn

    def init_schema(self) -> None:
        self._ensure_conn().execute(_DDL)

    def add_reference(self, entity_id: str, embedding: Sequence[float]) -> None:
        self._ensure_conn().execute(
            "INSERT INTO embeddings (entity_id, vector) VALUES (%s, %s)",
            (entity_id, list(embedding)),
        )

    def delete_entity(self, entity_id: str) -> None:
        # Borrado real (GDPR / cierre de emergencia — ADR-0007).
        self._ensure_conn().execute("DELETE FROM embeddings WHERE entity_id = %s", (entity_id,))

    def all_references(self) -> list[tuple[str, tuple[float, ...]]]:
        cur = self._ensure_conn().execute("SELECT entity_id, vector FROM embeddings")
        return [(eid, tuple(vec)) for eid, vec in cur.fetchall()]
