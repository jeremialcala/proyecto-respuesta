"""Caso de uso: resolver un probe de terreno contra el clúster y producir candidatos.

Orquesta el pipeline puro (búsqueda ANN → banda por drift → ruteo → fusión) usando los puertos.
No conoce infraestructura concreta. Publica `candidate.generated` por cada candidato no descartado
(catálogo y sobre de eventos: ADR-0011). En el MVP el scoring es **solo-rostro** (ADR-0013): el
contexto no suele traer geo/text, por lo que la fusión usa solo la señal facial.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import DriftParams, FusionWeights
from ..domain import drift, fusion
from ..domain.models import Candidate, Routing, Signals
from .ports import AnnIndex, EventBus


@dataclass(frozen=True)
class ProbeContext:
    """Contexto del reporte de terreno (encontrado) a resolver."""
    embedding: tuple[float, ...]
    report_id: Optional[str] = None
    is_minor: bool = False
    age_gap_years: float = 0.0
    geo_sim: Optional[float] = None   # MVP solo-rostro: normalmente None (ADR-0013)
    text_sim: Optional[float] = None  # MVP solo-rostro: normalmente None (ADR-0013)


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
        """Devuelve los candidatos no descartados y publica `candidate.generated` por cada uno."""
        candidates: list[Candidate] = []
        for entity_id, distance in self._index.search(probe.embedding, self._k):
            band = drift.compute_band(distance, probe.age_gap_years, probe.is_minor, self._dp)
            routing = drift.route(band, probe.is_minor)
            if routing is Routing.DISCARD:
                continue

            face_sim = fusion.sim_from_distance(distance)
            fused = fusion.fuse(
                Signals(face=face_sim, geo=probe.geo_sim, text=probe.text_sim),
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
            # Payload alineado al catálogo `candidate.generated` (ADR-0011); el bus añade el sobre.
            self._bus.publish(
                "candidate.generated",
                {
                    "report_id": probe.report_id,
                    "entity_id": entity_id,
                    "match_found": True,
                    "face_distance": distance,
                    "face_score": face_sim,
                    "band": band.value,
                    "routing": routing.value,
                    "fused_score": fused,
                },
            )
        return candidates
