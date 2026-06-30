"""Modelos de dominio del motor de matching."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Band(Enum):
    """Banda de la señal facial según distancia y tolerancia a drift."""
    STRONG = "strong"                    # d <= tau0
    DRIFT_TOLERATED = "drift_tolerated"  # tau0 < d <= tau0 + delta
    DISCARD = "discard"                  # d > tau0 + delta


class Routing(Enum):
    """A dónde va un candidato. El face-match NUNCA produce auto-confirmación por sí solo."""
    DISCARD = "discard"
    COORDINATOR = "coordinator"  # revisión humana obligatoria
    FUSE = "fuse"                # continúa a fusión multi-señal (no es auto-confirmación)


@dataclass(frozen=True)
class FaceQuality:
    size_px: int
    blur_var: float
    yaw: float
    pitch: float


@dataclass(frozen=True)
class Signals:
    """Similitudes en [0,1] (1 = más parecido). None = señal ausente (peso dinámico → 0)."""
    face: Optional[float] = None
    geo: Optional[float] = None
    text: Optional[float] = None


@dataclass(frozen=True)
class BBox:
    """Caja del rostro en píxeles de la imagen (para recortar y ubicar). ADR-0016."""
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


@dataclass(frozen=True)
class FaceMap:
    """'Mapa del rostro': embedding de una persona detectada + su calidad y geometría (ADR-0013/0016)."""
    embedding: tuple[float, ...]
    quality: FaceQuality
    bbox: Optional[BBox] = None   # geometría de detección (ADR-0016); None si el detector no la aporta
    det_score: float = 0.0        # confianza del detector SCRFD (ADR-0016)


@dataclass(frozen=True)
class PendingFace:
    """Un rostro candidato dentro de una desambiguación (ADR-0016). Solo el elegido se enrola."""
    index: int
    embedding: tuple[float, ...]
    bbox: Optional[BBox]
    det_score: float
    crop_ref: Optional[str] = None   # recorte efímero en la bóveda


@dataclass(frozen=True)
class PendingEnrollment:
    """Desambiguación multi-rostro en curso (ADR-0016). Persistida con TTL; clave de idempotencia."""
    disambiguation_id: str
    entity_id: str
    report_id: Optional[str]
    faces: tuple[PendingFace, ...]
    conversation_key: Optional[str]   # para que el chatbot responda al reportante (ADR-0015)
    created_at: str
    expires_at: str
    status: str = "pending"           # pending | resolved | expired
    reporter: Optional[dict] = None   # {bot_id, channel, contact_ref}: para avisar al cerrar (ADR-0016)
    media_ref: Optional[str] = None   # foto original del reporte: imagen del cierre al enrolar (ADR-0020)


@dataclass(frozen=True)
class Candidate:
    """Resultado de comparar un probe de terreno contra una entidad del clúster."""
    entity_id: str
    face_distance: float
    band: Band
    routing: Routing
    fused_score: Optional[float] = None
