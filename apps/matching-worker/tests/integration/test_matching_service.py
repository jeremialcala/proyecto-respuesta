"""Integración del MatchingService con puertos falsos (fakes)."""
from matching_worker.application.matching_service import MatchingService, ProbeContext
from matching_worker.domain.models import Routing


class FakeIndex:
    def __init__(self, results):
        self._results = results

    def rebuild_from(self, store):  # no-op
        pass

    def search(self, embedding, k):
        return self._results[:k]


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))


def make_service(results):
    bus = FakeBus()
    svc = MatchingService(index=FakeIndex(results), bus=bus)
    return svc, bus


def test_strong_adult_match_routes_to_fuse_and_publishes():
    svc, bus = make_service([("e1", 0.5)])
    out = svc.resolve(ProbeContext(embedding=(0.1, 0.2)))
    assert len(out) == 1
    assert out[0].entity_id == "e1"
    assert out[0].routing is Routing.FUSE
    assert out[0].fused_score == 0.5  # solo señal facial: 1 - 0.5
    assert bus.events and bus.events[0][0] == "candidate.generated"


def test_far_match_is_discarded():
    svc, bus = make_service([("e1", 0.95)])
    out = svc.resolve(ProbeContext(embedding=(0.0,), age_gap_years=0))
    assert out == []
    assert bus.events == []  # nada que publicar


def test_minor_strong_match_forces_coordinator():
    """Invariante: un menor con match fuerte va a coordinador, nunca por la vía automática."""
    svc, _ = make_service([("e1", 0.4)])
    out = svc.resolve(ProbeContext(embedding=(0.0,), is_minor=True))
    assert out[0].routing is Routing.COORDINATOR


def test_fusion_uses_geo_and_text_when_present():
    svc, _ = make_service([("e1", 0.2)])  # face sim = 0.8
    out = svc.resolve(ProbeContext(embedding=(0.0,), geo_sim=0.6, text_sim=0.4))
    # 0.6*0.8 + 0.25*0.6 + 0.15*0.4 = 0.69
    assert round(out[0].fused_score, 4) == 0.69


def test_candidate_payload_aligns_with_adr0011():
    """El payload de candidate.generated lleva report_id, face_score y match_found (ADR-0011)."""
    svc, bus = make_service([("e1", 0.4)])
    svc.resolve(ProbeContext(embedding=(0.0,), report_id="rep_1"))
    event, payload = bus.events[0]
    assert event == "candidate.generated"
    assert payload["report_id"] == "rep_1"
    assert payload["match_found"] is True
    assert round(payload["face_score"], 4) == 0.6  # 1 - 0.4
    assert payload["entity_id"] == "e1"
