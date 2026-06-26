"""Puertos (interfaces) de la capa de aplicación. Los adaptadores los implementan.

Regla de dependencia (Clean Architecture): el dominio y la aplicación NO conocen la
infraestructura; dependen solo de estas abstracciones.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from ..domain.models import FaceMap


class FaceMapper(Protocol):
    """Detecta rostros y genera embeddings ArcFace/IResNet100 de 512-d (ADR-0013)."""

    def map_image(self, image_bytes: bytes) -> list[FaceMap]:
        """Un FaceMap por rostro detectado en una imagen."""
        ...

    def map_video(self, video_bytes: bytes) -> list[FaceMap]:
        """Probes agregados por persona (tracking + Hierarchical Windowing)."""
        ...


class EmbeddingStore(Protocol):
    """Fuente de verdad de los embeddings (pgvector, 512-d). Soporta borrado real (GDPR)."""

    def add_reference(self, entity_id: str, embedding: Sequence[float]) -> None: ...
    def delete_entity(self, entity_id: str) -> None: ...
    def all_references(self) -> list[tuple[str, tuple[float, ...]]]: ...


class AnnIndex(Protocol):
    """Índice ANN en memoria (FAISS HNSW, d=512). Se refresca desde el EmbeddingStore."""

    def rebuild_from(self, store: EmbeddingStore) -> None: ...
    def search(self, embedding: Sequence[float], k: int) -> list[tuple[str, float]]:
        """Devuelve [(entity_id, distancia_coseno)] ordenado por cercanía."""
        ...


class EventBus(Protocol):
    """Publicación de eventos sobre AWS SQS/SNS (ADR-0012); envuelve en el sobre estándar (ADR-0011)."""

    def publish(self, event: str, payload: dict) -> None: ...
