"""Parse del payload de Meta: object e ids de mensaje (idempotencia)."""
from webhook_gateway.domain.meta_payload import summarize


def test_whatsapp_message_ids_and_object():
    raw = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"id": "wamid.AAA", "type": "text"},
            {"id": "wamid.BBB", "type": "image"},
        ]}}]}],
    }
    s = summarize(raw)
    assert s.object_type == "whatsapp_business_account"
    assert s.message_ids == ("wamid.AAA", "wamid.BBB")
    assert s.dedup_key == "wamid.AAA"


def test_messenger_mid_supported():
    raw = {"object": "page", "entry": [{"messaging": [{"message": {"mid": "m_1"}}]}]}
    assert summarize(raw).message_ids == ("m_1",)


def test_empty_payload_has_no_dedup_key():
    s = summarize({"object": "whatsapp_business_account", "entry": []})
    assert s.message_ids == ()
    assert s.dedup_key is None


def test_invalid_payload_raises():
    import pytest
    with pytest.raises(ValueError):
        summarize("not-a-dict")
