"""Máquina de estados y matriz de autoridad (charter)."""
from core_backend.domain.models import Mechanism, PersonState
from core_backend.domain.state_machine import can_transition, requires_evidence


def test_autorreporte_only_a_salvo():
    assert can_transition(PersonState.A_SALVO, Mechanism.AUTORREPORTE)
    assert not can_transition(PersonState.FALLECIDO, Mechanism.AUTORREPORTE)


def test_fallecido_only_by_authority():
    assert can_transition(PersonState.FALLECIDO, Mechanism.AUTORIDAD)
    for m in (Mechanism.RESCATISTA, Mechanism.COORDINADOR, Mechanism.AUTORREPORTE):
        assert not can_transition(PersonState.FALLECIDO, m)


def test_critico_coordinador_or_authority():
    assert can_transition(PersonState.LOCALIZADO_CRITICO, Mechanism.COORDINADOR)
    assert can_transition(PersonState.LOCALIZADO_CRITICO, Mechanism.AUTORIDAD)
    assert not can_transition(PersonState.LOCALIZADO_CRITICO, Mechanism.RESCATISTA)


def test_evidence_required_for_deceased():
    assert requires_evidence(PersonState.FALLECIDO) is True
    assert requires_evidence(PersonState.A_SALVO) is False
