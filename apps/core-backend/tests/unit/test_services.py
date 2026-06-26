"""Servicios del core: intake (report.ingested) y state (state.changed) con auditoría encadenada."""
from core_backend.config import CoreConfig
from core_backend.adapters.memory_stores import MemoryStores
from core_backend.application.chained_audit import ChainedAudit
from core_backend.application.intake_service import IntakeService
from core_backend.application.state_service import StateService, TransitionError
from core_backend.domain.audit import verify_chain
from core_backend.domain.models import Mechanism, PersonState


class FakePub:
    def __init__(self):
        self.events = []

    def publish(self, topic, env):
        self.events.append((topic, env))


def _wire():
    cfg = CoreConfig(producer="core-backend")
    stores, pub = MemoryStores(), FakePub()
    audit = ChainedAudit(stores)
    return cfg, stores, pub, IntakeService(cfg, stores, stores, audit, pub), StateService(cfg, stores, audit, pub)


def _report_env(**over):
    p = {"intention": "desaparecido", "subject_name": "Juan Pérez", "id_type": "V",
         "id_number": "18452931", "source": "chatbot:whatsapp", "ultima_ubicacion": "Caracas"}
    p.update(over)
    return {"event_id": "evt-1", "payload": p}


def test_intake_accepts_and_emits_report_ingested():
    cfg, stores, pub, intake, _ = _wire()
    res = intake.handle(_report_env())
    assert res.accepted and res.report_id.startswith("rep_") and res.entity_id.startswith("ent_")
    topics = [t for t, _ in pub.events]
    assert "report.ingested" in topics
    env = next(e for t, e in pub.events if t == "report.ingested")
    assert env["payload"]["report_id"] == res.report_id
    # esquema dinámico: el atributo opcional quedó en attributes
    _, report = stores.reports[res.report_id]
    assert report.attributes.get("ultima_ubicacion") == "Caracas"
    # auditoría encadenada íntegra
    assert verify_chain(stores.audit) is True


def test_intake_rejects_incomplete():
    cfg, stores, pub, intake, _ = _wire()
    res = intake.handle({"event_id": "e", "payload": {"subject_name": "Juan", "source": "x"}})
    assert res.accepted is False
    assert all(t != "report.ingested" for t, _ in pub.events)
    assert stores.audit and stores.audit[-1].action == "report.rejected"


def test_state_transition_allowed_emits_event_and_audits():
    cfg, stores, pub, intake, state = _wire()
    stores.create_entity("ent_1", PersonState.DESAPARECIDO)
    res = state.transition("ent_1", PersonState.A_SALVO, Mechanism.AUTORREPORTE, "self")
    assert res.to_state is PersonState.A_SALVO
    assert stores.get_state("ent_1") is PersonState.A_SALVO
    assert any(t == "state.changed" for t, _ in pub.events)
    assert verify_chain(stores.audit) is True


def test_state_transition_denied_by_authority_matrix():
    cfg, stores, pub, intake, state = _wire()
    stores.create_entity("ent_2", PersonState.DESAPARECIDO)
    try:
        state.transition("ent_2", PersonState.FALLECIDO, Mechanism.RESCATISTA, "resc-1")
        assert False, "debió denegar"
    except TransitionError:
        pass
    assert all(t != "state.changed" for t, _ in pub.events)
    assert stores.audit[-1].action == "state.denied"


def test_deceased_requires_evidence():
    cfg, stores, pub, intake, state = _wire()
    stores.create_entity("ent_3", PersonState.LOCALIZADO_CRITICO)
    try:
        state.transition("ent_3", PersonState.FALLECIDO, Mechanism.AUTORIDAD, "auth-1")
        assert False
    except TransitionError:
        pass
    # con evidencia, procede
    res = state.transition("ent_3", PersonState.FALLECIDO, Mechanism.AUTORIDAD, "auth-1",
                           evidence_ref="acta-123")
    assert res.to_state is PersonState.FALLECIDO
