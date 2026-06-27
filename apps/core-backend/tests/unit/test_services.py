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


class FakeCorrelation:
    """Correlación en memoria (foto↔reporte) para tests, con la misma semántica que el adaptador Redis."""
    def __init__(self):
        self.media = {}
        self.report = {}

    def remember_media(self, contact_ref, media_ref):
        if contact_ref and media_ref:
            self.media[contact_ref] = media_ref

    def get_media(self, contact_ref):
        return self.media.get(contact_ref)

    def remember_report(self, contact_ref, report_id, entity_id, reporter=None):
        if contact_ref:
            self.report[contact_ref] = {"report_id": report_id, "entity_id": entity_id,
                                        "bot_id": (reporter or {}).get("bot_id", ""),
                                        "channel": (reporter or {}).get("channel", "")}

    def get_report(self, contact_ref):
        return self.report.get(contact_ref)


def _wire():
    cfg = CoreConfig(producer="core-backend")
    stores, pub = MemoryStores(), FakePub()
    audit = ChainedAudit(stores)
    return cfg, stores, pub, IntakeService(cfg, stores, stores, audit, pub), StateService(cfg, stores, audit, pub)


def _wire_corr():
    cfg = CoreConfig(producer="core-backend")
    stores, pub, corr = MemoryStores(), FakePub(), FakeCorrelation()
    intake = IntakeService(cfg, stores, stores, ChainedAudit(stores), pub, corr)
    return cfg, stores, pub, corr, intake


def _media_env(contact_ref="wa:5215555", media_ref="s3://respuesta-media/media/x/1", scan="clean"):
    return {"event_id": "evt-media", "event_type": "media.stored",
            "payload": {"contact_ref": contact_ref, "media_ref": media_ref,
                        "media_type": "image", "scan": scan}}


def _ingested(pub):
    return next(e for t, e in pub.events if t == "report.ingested")


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


def test_photo_before_report_links_media():
    """La foto llega antes: media.stored sola no emite; el report.received la encuentra y la vincula."""
    cfg, stores, pub, corr, intake = _wire_corr()
    intake.on_media_stored(_media_env(contact_ref="wa:c1", media_ref="s3://b/m/c1/1"))
    assert all(t != "report.ingested" for t, _ in pub.events)   # aún no hay reporte → no emite
    intake.handle(_report_env(contact_ref="wa:c1"))
    assert _ingested(pub)["payload"]["media_ref"] == "s3://b/m/c1/1"


def test_report_before_photo_links_on_media_stored():
    """El reporte llega antes (sin foto); media.stored re-emite report.ingested con el media_ref."""
    cfg, stores, pub, corr, intake = _wire_corr()
    res = intake.handle(_report_env(contact_ref="wa:c2", bot_id="bot-1", channel="whatsapp"))
    assert _ingested(pub)["payload"]["media_ref"] is None       # aún sin foto
    intake.on_media_stored(_media_env(contact_ref="wa:c2", media_ref="s3://b/m/c2/9"))
    ingested = [e for t, e in pub.events if t == "report.ingested"]
    assert len(ingested) == 2                                   # re-emitido al llegar la foto
    assert ingested[1]["payload"]["media_ref"] == "s3://b/m/c2/9"
    assert ingested[1]["payload"]["entity_id"] == res.entity_id
    assert ingested[1]["payload"]["source"] == "media.stored"
    # la identidad del reportante viaja para poder avisarle al cerrar (ADR-0016)
    assert ingested[1]["payload"]["contact_ref"] == "wa:c2"
    assert ingested[1]["payload"]["bot_id"] == "bot-1"


def test_media_stored_without_report_does_not_emit():
    cfg, stores, pub, corr, intake = _wire_corr()
    intake.on_media_stored(_media_env(contact_ref="wa:c3"))
    assert all(t != "report.ingested" for t, _ in pub.events)
    assert corr.get_media("wa:c3")                              # recordada para cuando llegue el reporte


def test_payload_media_ref_takes_precedence():
    cfg, stores, pub, corr, intake = _wire_corr()
    intake.handle(_report_env(contact_ref="wa:c4", media_ref="s3://explicit/ref"))
    assert _ingested(pub)["payload"]["media_ref"] == "s3://explicit/ref"


def test_non_clean_media_is_ignored():
    cfg, stores, pub, corr, intake = _wire_corr()
    intake.handle(_report_env(contact_ref="wa:c5"))
    intake.on_media_stored(_media_env(contact_ref="wa:c5", scan="quarantined"))
    ingested = [e for t, e in pub.events if t == "report.ingested"]
    assert len(ingested) == 1                                   # no re-emite con media en cuarentena


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
