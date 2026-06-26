"""Compuerta de calidad (ADR-0004): descarta rostros de baja calidad antes de generar embeddings."""
from __future__ import annotations

from ..config import QualityThresholds
from .models import FaceQuality


def passes(q: FaceQuality, t: QualityThresholds) -> bool:
    """True si el rostro supera tamaño mínimo, nitidez y pose aceptable."""
    return (
        q.size_px >= t.min_size_px
        and q.blur_var >= t.min_blur_var
        and abs(q.yaw) <= t.max_abs_yaw
        and abs(q.pitch) <= t.max_abs_pitch
    )
