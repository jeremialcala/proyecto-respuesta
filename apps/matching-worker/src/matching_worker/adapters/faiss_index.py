"""Adaptador FAISS: índice ANN en memoria `IndexIDMap2(IndexHNSWFlat, M=32)`, **d=512** (ADR-0013).

pgvector es la fuente de verdad; HNSW no borra in-place → el refresco se hace **reconstruyendo**
desde pgvector. Métrica coseno (vectores ArcFace ya normalizados → inner product). `faiss` se
importa de forma perezosa. Afinado de carga/refresco: fase 03.
"""
from __future__ import annotations

from typing import Sequence

from ..config import EMBEDDING_DIM, FaissParams
from .pgvector_store import PgvectorEmbeddingStore


class FaissAnnIndex:
    def __init__(self, dim: int = EMBEDDING_DIM, params: FaissParams | None = None) -> None:
        self._dim = dim
        self._params = params or FaissParams()
        self._index = None
        self._ids: list[str] = []

    def _ensure_index(self):
        if self._index is None:
            import faiss  # import perezoso
            base = faiss.IndexHNSWFlat(self._dim, self._params.m, faiss.METRIC_INNER_PRODUCT)
            base.hnsw.efConstruction = self._params.ef_construction
            base.hnsw.efSearch = self._params.ef_search
            self._index = faiss.IndexIDMap2(base)
        return self._index

    def rebuild_from(self, store: PgvectorEmbeddingStore) -> None:
        import faiss
        import numpy as np
        refs = store.all_references()
        self._index = None
        idx = self._ensure_index()
        self._ids = [eid for eid, _ in refs]
        if not refs:
            return
        vecs = np.asarray([v for _, v in refs], dtype="float32")
        faiss.normalize_L2(vecs)  # coseno vía inner product
        idx.add_with_ids(vecs, np.arange(len(refs), dtype="int64"))

    def search(self, embedding: Sequence[float], k: int) -> list[tuple[str, float]]:
        import faiss
        import numpy as np
        idx = self._ensure_index()
        q = np.asarray([list(embedding)], dtype="float32")
        faiss.normalize_L2(q)
        sims, ids = idx.search(q, k)
        out: list[tuple[str, float]] = []
        for sim, i in zip(sims[0], ids[0]):
            if i < 0:
                continue
            distance = 1.0 - float(sim)  # inner product (coseno) → distancia coseno [0,1]
            out.append((self._ids[int(i)], distance))
        return out
