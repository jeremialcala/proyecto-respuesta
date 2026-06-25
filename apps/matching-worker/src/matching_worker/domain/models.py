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
class FaceMap:
    """'Mapa del rostro': embedding de una persona detectada + su calidad."""
    embedding: tuple[float, ...]
    quality: FaceQuality


@dataclass(frozen=True)
class Candidate:
    """Resultado de comparar un probe de terreno contra una entidad del clúster."""
    entity_id: str
    face_distance: float
    band: Band
    routing: Routing
    fused_score: Optional[float] = None
