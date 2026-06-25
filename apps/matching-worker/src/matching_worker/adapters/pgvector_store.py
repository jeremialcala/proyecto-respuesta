"""Adaptador pgvector: fuente de verdad de embeddings (durable, borrado GDPR). Esqueleto.

Implementación pendiente (fase 03):
- Tabla `embeddings(entity_id, vector vector(128), created_at, ...)`.
- add_reference: INSERT; delete_entity: DELETE (borrado real, cierre de emergencia).
- all_references: SELECT para reconstruir el índice FAISS.
"""
from __future__ import annotations

from typing import Sequence


class PgvectorEmbeddingStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        # TODO(fase-03): conexión psycopg + pgvector

    def add_reference(self, entity_id: str, embedding: Sequence[float]) -> None:
        raise NotImplementedError("TODO(fase-03): INSERT en pgvector")

    def delete_entity(self, entity_id: str) -> None:
        raise NotImplementedError("TODO(fase-03): DELETE en pgvector (borrado GDPR)")

    def all_references(self) -> list[tuple[str, tuple[float, ...]]]:
        raise NotImplementedError("TODO(fase-03): SELECT de referencias")
