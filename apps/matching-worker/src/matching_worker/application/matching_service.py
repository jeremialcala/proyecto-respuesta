"""Caso de uso: resolver un probe de terreno contra el clúster y producir candidatos.

Orquesta el pipeline puro (búsqueda ANN → banda por drift → ruteo → fusión) usando los puertos.
No conoce infraestructura concreta. Publica `candidate.generated` por cada candidato no descartado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..config import DriftParams, FusionWeights
from ..domain import drift, fusion
from ..domain.models import Candidate, Routing, Signals
from .ports import AnnIndex, EventBus


@dataclass(frozen=True)
class ProbeContext:
    """Contexto del reporte de terreno (encontrado) a resolver."""
    embedding: tuple[float, ...]
    is_minor: bool = False
    age_gap_years: float = 0.0
    geo_sim: Optional[float] = None
    text_sim: Optional[float] = None


class MatchingService:
    def __init__(
        self,
        index: AnnIndex,
        bus: EventBus,
        drift_params: DriftParams | None = None,
        weights: FusionWeights | None = None,
        top_k: int = 10,
    ) -> None:
        self._index = index
        self._bus = bus
        self._dp = drift_params or DriftParams()
        self._w = weights or FusionWeights()
        self._k = top_k

    def resolve(self, probe: ProbeContext) -> list[Candidate]:
        """Devuelve los candidatos no descartados y publica un evento por cada uno."""
        candidates: list[Candidate] = []
        for entity_id, distance in self._index.search(probe.embedding, self._k):
            band = drift.compute_band(distance, probe.age_gap_years, probe.is_minor, self._dp)
            routing = drift.route(band, probe.is_minor)
            if routing is Routing.DISCARD:
                continue

            fused = fusion.fuse(
                Signals(
                    face=fusion.sim_from_distance(distance),
                    geo=probe.geo_sim,
                    text=probe.text_sim,
                ),
                self._w,
            )
            candidate = Candidate(
                entity_id=entity_id,
                face_distance=distance,
                band=band,
                routing=routing,
                fused_score=fused,
            )
            candidates.append(candidate)
            self._bus.publish(
                "candidate.generated",
                {
                    "entity_id": entity_id,
                    "face_distance": distance,
                    "band": band.value,
                    "routing": routing.value,
                    "fused_score": fused,
                },
            )
        return candidates
