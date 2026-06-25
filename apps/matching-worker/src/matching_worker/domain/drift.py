"""Tolerancia a drift de edad (ADR-0004).

Distancia coseno `d` en [0,1] (0 = idéntico). El margen de drift amplía el conjunto de
candidatos pero **empuja a revisión de coordinador, nunca a auto-aceptación**. Los menores van
siempre a coordinador.
"""
from __future__ import annotations

from ..config import DriftParams
from .models import Band, Routing


def drift_margin(age_gap_years: float, is_minor: bool, p: DriftParams) -> float:
    """Δ(edad, age_gap) = min(Δ_max, α·age_gap + β·[es_menor])."""
    if age_gap_years < 0:
        raise ValueError("age_gap_years no puede ser negativo")
    raw = p.alpha * age_gap_years + (p.beta if is_minor else 0.0)
    return min(p.delta_max, raw)


def compute_band(distance: float, age_gap_years: float, is_minor: bool, p: DriftParams) -> Band:
    """Clasifica la señal facial en STRONG / DRIFT_TOLERATED / DISCARD."""
    if not 0.0 <= distance <= 1.0:
        raise ValueError("distance debe estar en [0,1]")
    if distance <= p.tau0:
        return Band.STRONG
    if distance <= p.tau0 + drift_margin(age_gap_years, is_minor, p):
        return Band.DRIFT_TOLERATED
    return Band.DISCARD


def route(band: Band, is_minor: bool) -> Routing:
    """Invariante de seguridad: la señal facial nunca auto-confirma.

    - DISCARD          → DISCARD
    - DRIFT_TOLERATED  → COORDINATOR (siempre humano)
    - STRONG           → COORDINATOR si es menor; si no, FUSE (continúa a fusión, no auto-confirma)
    """
    if band is Band.DISCARD:
        return Routing.DISCARD
    if band is Band.DRIFT_TOLERATED:
        return Routing.COORDINATOR
    return Routing.COORDINATOR if is_minor else Routing.FUSE
