"""Reparto del Meta Handler: text/location→inbound.text (JWE), image→inbound.media (ADR-0005)."""
import json

from meta_handler.config import HandlerConfig
from meta_handler.application.handler_service import HandlerService


class FakePub:
    def __init__(self):
        self.text = []
        self.media = []

    def publish_text(self, env):
        self.text.append(env)

    def publish_media(self, env):
        self.media.append(env)


class SpyCipher:
    def encrypt(self, plaintext):
        return "ENC(" + plaintext + ")"


class SpyLog:
    def __init__(self):
        self.actions = []

    def record_action(self, event_id, action, status, detail=""):
        self.actions.append((action, status, detail))


def _svc():
    pub, log = FakePub(), SpyLog()
    svc = HandlerService(HandlerConfig(producer="meta-handler"), pub, SpyCipher(), log)
    return svc, pub, log


def _env(messages, bot_id="bot-1", event_id="evt-1"):
    return {"event_id": event_id, "event_type": "meta.received",
            "payload": {"bot_id": bot_id, "object": "whatsapp_business_account",
                        "raw": {"object": "whatsapp_business_account",
                                "entry": [{"changes": [{"value": {"messages": messages}}]}]}}}


def test_text_dispatched_to_inbound_text_encrypted():
    svc, pub, _ = _svc()
    res = svc.handle(_env([{"id": "wamid.1", "from": "584120000000", "type": "text",
                            "text": {"body": "hola"}}]))
    assert res.text == 1 and res.media == 0
    env = pub.text[0]
    assert env["event_type"] == "inbound.text"
    assert env["payload"]["contact_ref"] == "584120000000"
    assert env["payload"]["jwe_body"].startswith("ENC(")
    body = json.loads(env["payload"]["jwe_body"][4:-1])
    assert body == {"kind": "text", "text": "hola"}


def test_image_dispatched_to_inbound_media_without_binary():
    svc, pub, _ = _svc()
    res = svc.handle(_env([{"id": "wamid.2", "from": "x", "type": "image",
                            "image": {"id": "media-99", "mime_type": "image/jpeg"}}]))
    assert res.media == 1
    env = pub.media[0]
    assert env["event_type"] == "inbound.media"
    assert env["payload"]["media_id"] == "media-99"
    assert "binary" not in env["payload"] and "image" not in env["payload"]


def test_image_with_caption_dispatches_media_and_text():
    """Imagen con pie de foto → inbound.media (foto) + inbound.text (el caption = el reporte)."""
    svc, pub, _ = _svc()
    res = svc.handle(_env([{"id": "wamid.2b", "from": "584120000000", "type": "image",
                            "image": {"id": "media-50", "mime_type": "image/jpeg",
                                      "caption": "El es Harry Gonzalez, visto en Playa Grande"}}]))
    assert res.media == 1 and res.text == 1
    assert pub.media[0]["payload"]["media_id"] == "media-50"
    body = json.loads(pub.text[0]["payload"]["jwe_body"][4:-1])
    assert body == {"kind": "text", "text": "El es Harry Gonzalez, visto en Playa Grande"}


def test_image_without_caption_dispatches_only_media():
    svc, pub, _ = _svc()
    res = svc.handle(_env([{"id": "wamid.2d", "from": "x", "type": "image",
                            "image": {"id": "m", "mime_type": "image/jpeg"}}]))
    assert res.media == 1 and res.text == 0 and pub.text == []


def test_location_goes_to_inbound_text_as_location():
    svc, pub, _ = _svc()
    svc.handle(_env([{"id": "wamid.3", "from": "x", "type": "location",
                      "location": {"latitude": 10.5, "longitude": -66.9}}]))
    body = json.loads(pub.text[0]["payload"]["jwe_body"][4:-1])
    assert body["kind"] == "location" and body["location"]["latitude"] == 10.5


def test_unsupported_is_skipped_and_logged():
    svc, pub, log = _svc()
    res = svc.handle(_env([{"id": "wamid.4", "from": "x", "type": "audio", "audio": {"id": "a"}}]))
    assert res.skipped == 1 and not pub.text and not pub.media
    assert any(s == "SKIP" for _, s, _ in log.actions)


def test_mixed_batch_counts():
    svc, pub, _ = _svc()
    res = svc.handle(_env([
        {"id": "1", "from": "a", "type": "text", "text": {"body": "hi"}},
        {"id": "2", "from": "a", "type": "image", "image": {"id": "m", "mime_type": "image/png"}},
        {"id": "3", "from": "a", "type": "location", "location": {"latitude": 1.0, "longitude": 2.0}},
    ]))
    assert (res.text, res.media, res.skipped) == (2, 1, 0)
