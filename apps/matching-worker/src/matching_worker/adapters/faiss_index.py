"""Adaptador FAISS: índice ANN en memoria `IndexIDMap2(IndexHNSWFlat, M=32)`. Esqueleto.

Implementación pendiente (fase 03):
- Construir IndexHNSWFlat(d, M) con efConstruction/efSearch (config.FaissParams), métrica coseno
  (normalizar vectores → inner product).
- rebuild_from(store): cargar todas las referencias desde pgvector (HNSW no borra in-place →
  el refresco se hace reconstruyendo desde la fuente de verdad).
- search: devolver [(entity_id, distancia_coseno)].
"""
from __future__ import annotations

from typing import Sequence

from ..config import FaissParams
from .pgvector_store import PgvectorEmbeddingStore


class FaissAnnIndex:
    def __init__(self, dim: int, params: FaissParams | None = None) -> None:
        self._dim = dim
        self._params = params or FaissParams()
        # TODO(fase-03): faiss.IndexIDMap2(faiss.IndexHNSWFlat(dim, params.m))

    def rebuild_from(self, store: PgvectorEmbeddingStore) -> None:
        raise NotImplementedError("TODO(fase-03): reconstruir HNSW desde pgvector")

    def search(self, embedding: Sequence[float], k: int) -> list[tuple[str, float]]:
        raise NotImplementedError("TODO(fase-03): búsqueda ANN coseno")
