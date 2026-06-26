"""Caso de uso: transición de estado según la matriz de autoridad (charter) y emisión de state.changed.

Valida que el mecanismo esté autorizado a fijar el estado; `fallecido` exige evidencia. Persiste,
registra la auditoría encadenada y publica `state.changed`. El sistema transmite, no deduce.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import CoreConfig
from ..domain.models import Mechanism, PersonState
from ..domain.state_machine import can_transition, requires_evidence
from .chained_audit import ChainedAudit
from .events import build_envelope
from .ports import EntityStore, EventPublisher


class TransitionError(Exception):
    pass


@dataclass(frozen=True)
class TransitionResult:
    entity_id: str
    to_state: PersonState


class StateService:
    def __init__(self, cfg: CoreConfig, entities: EntityStore, audit: ChainedAudit,
                 publisher: EventPublisher) -> None:
        self._cfg = cfg
        self._entities = entities
        self._audit = audit
        self._pub = publisher

    def transition(self, entity_id: str, to_state: PersonState, mechanism: Mechanism,
                   actor: str, evidence_ref: Optional[str] = None) -> TransitionResult:
        if not can_transition(to_state, mechanism):
            self._audit.record(actor, "state.denied",
                               {"entity_id": entity_id, "to": to_state.value,
                                "mechanism": mechanism.value})
            raise TransitionError(f"{mechanism.value} no puede fijar {to_state.value}")
        if requires_evidence(to_state) and not evidence_ref:
            raise TransitionError("fallecido requiere evidencia (acta/planilla)")

        from_state = self._entities.get_state(entity_id)
        self._entities.set_state(entity_id, to_state)
        self._audit.record(actor, "state.changed",
                           {"entity_id": entity_id, "from": from_state.value if from_state else None,
                            "to": to_state.value, "mechanism": mechanism.value,
                            "evidence_ref": evidence_ref})
        self._pub.publish("state.changed", build_envelope("state.changed", {
            "entity_id": entity_id, "from_state": from_state.value if from_state else None,
            "to_state": to_state.value, "mechanism": mechanism.value, "actor": actor,
        }, self._cfg.producer))
        return TransitionResult(entity_id=entity_id, to_state=to_state)
