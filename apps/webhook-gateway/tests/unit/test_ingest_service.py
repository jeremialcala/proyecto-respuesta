"""Servicio de ingesta del Gateway: handshake, firma, dedup, publicación (ADR-0005)."""
import json

from webhook_gateway.config import BotConfig, GatewayConfig
from webhook_gateway.domain.signature import compute_signature
from webhook_gateway.application.ingest_service import Decision, IngestService

BOT = "bot-1"
SECRET = "secret-xyz"
VERIFY = "verif-token"


class FakeIdem:
    def __init__(self, preexisting=()):
        self._seen = set(preexisting)

    def seen(self, key):
        if key in self._seen:
            return True
        self._seen.add(key)
        return False


class FakePublisher:
    def __init__(self):
        self.published = []

    def publish_raw(self, envelope):
        self.published.append(envelope)


def _cfg():
    return GatewayConfig(raw_queue_url="q", bots={BOT: BotConfig(BOT, VERIFY, SECRET)})


def _svc(idem=None, pub=None):
    pub = pub or FakePublisher()
    return IngestService(_cfg(), idem or FakeIdem(), pub), pub


def _body(ids=("wamid.1",), object_type="whatsapp_business_account"):
    raw = {"object": object_type, "entry": [{"changes": [{"value": {"messages": [
        {"id": i} for i in ids]}}]}]}
    b = json.dumps(raw).encode()
    return b, raw


def test_verify_subscription_ok_and_bad_token():
    svc, _ = _svc()
    assert svc.verify_subscription(BOT, "subscribe", VERIFY, "challenge-9") == "challenge-9"
    assert svc.verify_subscription(BOT, "subscribe", "mala", "x") is None
    assert svc.verify_subscription("desconocido", "subscribe", VERIFY, "x") is None


def test_accepted_publishes_envelope():
    svc, pub = _svc()
    body, raw = _body()
    res = svc.ingest(BOT, body, raw, compute_signature(SECRET, body))
    assert res.decision is Decision.ACCEPTED
    assert res.http_status == 200
    assert len(pub.published) == 1
    env = pub.published[0]
    assert env["event_type"] == "meta.received"
    assert env["producer"] == "webhook-gateway"
    assert env["payload"]["bot_id"] == BOT
    assert env["payload"]["raw"] == raw


def test_bad_signature_rejected_403_and_not_published():
    svc, pub = _svc()
    body, raw = _body()
    res = svc.ingest(BOT, body, raw, "sha256=deadbeef")
    assert res.decision is Decision.REJECTED_SIGNATURE
    assert res.http_status == 403
    assert pub.published == []


def test_unknown_bot_rejected():
    svc, _ = _svc()
    body, raw = _body()
    res = svc.ingest("otro-bot", body, raw, compute_signature(SECRET, body))
    assert res.decision is Decision.REJECTED_UNKNOWN_BOT
    assert res.http_status == 403


def test_duplicate_is_acked_but_not_published():
    idem = FakeIdem(preexisting={f"{BOT}:wamid.1"})
    pub = FakePublisher()
    svc, _ = _svc(idem=idem, pub=pub)
    body, raw = _body(ids=("wamid.1",))
    res = svc.ingest(BOT, body, raw, compute_signature(SECRET, body))
    assert res.decision is Decision.DUPLICATE
    assert res.http_status == 200
    assert pub.published == []


def test_unsupported_object_not_published():
    svc, pub = _svc()
    body, raw = _body(object_type="instagram")
    res = svc.ingest(BOT, body, raw, compute_signature(SECRET, body))
    assert res.decision is Decision.REJECTED_OBJECT
    assert res.http_status == 200
    assert pub.published == []
