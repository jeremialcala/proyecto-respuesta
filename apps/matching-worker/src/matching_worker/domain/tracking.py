"""Agrupación de detecciones por track en video (ADR-0004).

Una detección se une a un track por continuidad espacial (IoU) **o** re-identificación por
embedding. El umbral de re-id es MÁS estricto que el del match cruzado (reid_distance < tau0)
para no fundir personas distintas en un mismo track.
"""
from __future__ import annotations

from ..config import DriftParams, TrackingParams


def should_join(distance: float, iou: float, p: TrackingParams) -> bool:
    """True si la detección pertenece al track (continuidad espacial o re-id por embedding)."""
    return iou >= p.min_iou or distance < p.reid_distance


def reid_is_stricter_than_match(tp: TrackingParams, dp: DriftParams) -> bool:
    """Invariante: el umbral de agrupación por track debe ser más estricto que el de match."""
    return tp.reid_distance < dp.tau0
