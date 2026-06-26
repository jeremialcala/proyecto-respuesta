"""Fusión multi-señal con pesos dinámicos (ADR-0004).

    Score_Final = Σ(W_i · S_i) / Σ(W_i)   sobre las señales presentes.

Las señales ausentes (None) se excluyen → su peso efectivo es 0, de modo que la falta de una
señal no rompe el score.
"""
from __future__ import annotations

from ..config import FusionWeights
from .models import Signals


def sim_from_distance(distance: float) -> float:
    """Convierte distancia coseno [0,1] en similitud [0,1] (1 = idéntico)."""
    if not 0.0 <= distance <= 1.0:
        raise ValueError("distance debe estar en [0,1]")
    return 1.0 - distance


def fuse(signals: Signals, weights: FusionWeights) -> float:
    """Combinación lineal ponderada, normalizada por los pesos de las señales presentes."""
    pairs = [
        (weights.face, signals.face),
        (weights.geo, signals.geo),
        (weights.text, signals.text),
    ]
    present = [(w, s) for (w, s) in pairs if s is not None]
    if not present:
        raise ValueError("no hay señales presentes para fusionar")
    for _, s in present:
        if not 0.0 <= s <= 1.0:
            raise ValueError("las similitudes deben estar en [0,1]")
    denom = sum(w for w, _ in present)
    if denom <= 0:
        raise ValueError("la suma de pesos presentes debe ser > 0")
    return sum(w * s for w, s in present) / denom
