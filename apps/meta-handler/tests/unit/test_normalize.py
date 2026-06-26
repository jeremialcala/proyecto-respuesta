"""Normalización del payload de Meta (ADR-0005)."""
from meta_handler.domain.normalize import normalize
from meta_handler.domain.models import Channel, MessageType


def _wa(messages):
    return {"object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {"messages": messages}}]}]}


def test_text_message():
    out = normalize(_wa([{"id": "wamid.1", "from": "584120000000", "type": "text",
                          "text": {"body": "hola"}}]))
    assert len(out) == 1
    m = out[0]
    assert m.channel is Channel.WHATSAPP and m.type is MessageType.TEXT
    assert m.contact_ref == "584120000000" and m.text == "hola"


def test_image_message_carries_media_id_not_binary():
    out = normalize(_wa([{"id": "wamid.2", "from": "x", "type": "image",
                          "image": {"id": "media-99", "mime_type": "image/jpeg"}}]))
    m = out[0]
    assert m.type is MessageType.IMAGE and m.media_id == "media-99" and m.mime_type == "image/jpeg"
    assert m.text is None


def test_location_message():
    out = normalize(_wa([{"id": "wamid.3", "from": "x", "type": "location",
                          "location": {"latitude": 10.5, "longitude": -66.9, "name": "Altamira"}}]))
    m = out[0]
    assert m.type is MessageType.LOCATION and m.location.latitude == 10.5
    assert m.location.longitude == -66.9 and m.location.address == "Altamira"


def test_unsupported_type():
    out = normalize(_wa([{"id": "wamid.4", "from": "x", "type": "audio", "audio": {"id": "a"}}]))
    assert out[0].type is MessageType.UNSUPPORTED


def test_non_whatsapp_object_maps_channel():
    out = normalize({"object": "page", "entry": [{"changes": [{"value": {"messages": [
        {"id": "m", "from": "f", "type": "text", "text": {"body": "x"}}]}}]}]})
    assert out[0].channel is Channel.MESSENGER


def test_invalid_raises():
    import pytest
    with pytest.raises(ValueError):
        normalize("nope")
