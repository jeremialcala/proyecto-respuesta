"""Parámetros del motor (ADR-0004). Valores iniciales; se calibran con datos reales (fase 04)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriftParams:
    """Tolerancia a drift de edad sobre la distancia coseno (0=idéntico .. 1=distinto)."""
    tau0: float = 0.60        # umbral base (clase ArcFace; SFace se calibra)
    alpha: float = 0.015      # margen por año de age_gap
    beta: float = 0.10        # bump adicional si es menor
    delta_max: float = 0.15   # tope del margen de drift


@dataclass(frozen=True)
class FusionWeights:
    """Pesos base de la fusión multi-señal (dinámicos: se anulan si falta la señal)."""
    face: float = 0.60
    geo: float = 0.25
    text: float = 0.15


@dataclass(frozen=True)
class QualityThresholds:
    min_size_px: int = 80      # lado mínimo del rostro
    min_blur_var: float = 40.0 # varianza del Laplaciano (más bajo = más borroso)
    max_abs_yaw: float = 45.0
    max_abs_pitch: float = 45.0


@dataclass(frozen=True)
class TrackingParams:
    """Agrupación de detecciones por track en video. Umbral MÁS estricto que el match (ADR-0004)."""
    reid_distance: float = 0.45   # debe ser < DriftParams.tau0
    min_iou: float = 0.30
    min_track_frames: int = 5


@dataclass(frozen=True)
class FaissParams:
    m: int = 32                # conexiones por nodo (biometría)
    ef_construction: int = 128
    ef_search: int = 32
