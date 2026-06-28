"""Puertos (interfaces) de la capa de aplicación. Los adaptadores los implementan.

Regla de dependencia (Clean Architecture): el dominio y la aplicación NO conocen la
infraestructura; dependen solo de estas abstracciones.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence

from ..domain.models import BBox, FaceMap, PendingEnrollment


class FaceMapper(Protocol):
    """Detecta rostros y genera embeddings ArcFace/IResNet100 de 512-d (ADR-0013)."""

    def map_image(self, image_bytes: bytes) -> list[FaceMap]:
        """Un FaceMap por rostro detectado en una imagen."""
        ...

    def map_video(self, video_bytes: bytes) -> list[FaceMap]:
        """Probes agregados por persona (tracking + Hierarchical Windowing)."""
        ...

    def crop_faces(self, image_bytes: bytes, bboxes: list[BBox]) -> list[bytes]:
        """Recorta cada rostro de la imagen para la desambiguación (ADR-0016)."""
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


class MediaGateway(Protocol):
    """Acceso a adjuntos cifrados de la bóveda (ADR-0005/0008). Recortes con TTL para minimizar (A04)."""

    def fetch(self, media_ref: str) -> bytes: ...
    def store_crops(self, crops: list[bytes], ttl_seconds: int) -> list[str]:
        """Guarda los recortes efímeros y devuelve sus `crop_ref`."""
        ...

    def delete_crops(self, crop_refs: list[str]) -> None: ...


class GrantRevoker(Protocol):
    """Revoca las concesiones del media-gateway emitidas para mostrar los recortes al reportante.

    Las URLs firmadas que sirvieron las miniaturas (ADR-0017) se revocan al purgar los recortes, para
    que dejen de servir antes incluso de su TTL (minimización, ADR-0016 §6). Best-effort: si falla, el
    TTL corto de la concesión es el respaldo.
    """

    def revoke_grants(self, *, report_id: Optional[str], media_refs: list[str]) -> None: ...


class PendingEnrollmentStore(Protocol):
    """Persistencia de desambiguaciones en curso (Postgres, con TTL). ADR-0016."""

    def save(self, pending: PendingEnrollment) -> None: ...
    def get(self, disambiguation_id: str) -> Optional[PendingEnrollment]: ...
    def mark_resolved(self, disambiguation_id: str) -> None: ...
    def purge_expired(self, now_iso: str) -> int:
        """Borra los pendientes vencidos; devuelve cuántos purgó."""
        ...
