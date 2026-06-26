"""Máquina de estados de persona y matriz de transiciones por autoridad (charter).

Invariantes de seguridad:
- `fallecido` y `localizado_critico` SOLO los fija la **autoridad** (mecanismo 4).
- El autorreporte solo puede fijar `a_salvo`.
- El sistema **transmite** el estado confirmado; nunca lo deduce.
"""
from __future__ import annotations

from .models import Mechanism, PersonState

# Estados que cada mecanismo puede fijar (charter, matriz de transiciones).
_ALLOWED: dict[Mechanism, frozenset[PersonState]] = {
    Mechanism.AUTORREPORTE: frozenset({PersonState.A_SALVO}),
    Mechanism.RESCATISTA: frozenset({PersonState.LOCALIZADO_ESTABLE}),
    Mechanism.COORDINADOR: frozenset({PersonState.LOCALIZADO_ESTABLE, PersonState.LOCALIZADO_CRITICO}),
    Mechanism.AUTORIDAD: frozenset({PersonState.LOCALIZADO_CRITICO, PersonState.FALLECIDO}),
}


def can_transition(to_state: PersonState, mechanism: Mechanism) -> bool:
    """¿El mecanismo está autorizado a fijar ese estado?"""
    return to_state in _ALLOWED.get(mechanism, frozenset())


def requires_evidence(to_state: PersonState) -> bool:
    """`fallecido` exige evidencia (acta/planilla) — ADR-0010."""
    return to_state is PersonState.FALLECIDO
