"""Verificación de firma X-Hub-Signature-256 (ADR-0005)."""
from webhook_gateway.domain.signature import compute_signature, verify_signature

SECRET = "app-secret-123"
BODY = b'{"object":"whatsapp_business_account","entry":[]}'


def test_valid_signature_passes():
    header = compute_signature(SECRET, BODY)
    assert header.startswith("sha256=")
    assert verify_signature(SECRET, BODY, header) is True


def test_tampered_body_fails():
    header = compute_signature(SECRET, BODY)
    assert verify_signature(SECRET, BODY + b"x", header) is False


def test_wrong_secret_fails():
    header = compute_signature("otra", BODY)
    assert verify_signature(SECRET, BODY, header) is False


def test_missing_or_malformed_header_fails():
    assert verify_signature(SECRET, BODY, None) is False
    assert verify_signature(SECRET, BODY, "md5=deadbeef") is False


def test_empty_secret_fails():
    header = compute_signature(SECRET, BODY)
    assert verify_signature("", BODY, header) is False
