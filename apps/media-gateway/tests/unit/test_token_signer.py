"""Firma/verificación HMAC del token (adaptador en proceso). ADR-0017 §7."""
from media_gateway.adapters.hmac_token_signer import HmacTokenSigner


def test_sign_then_verify_roundtrip():
    signer = HmacTokenSigner(b"secret-key")
    sig = signer.sign("tok123", 1000)
    assert signer.verify("tok123", 1000, sig)


def test_tampered_exp_fails():
    signer = HmacTokenSigner(b"secret-key")
    sig = signer.sign("tok123", 1000)
    assert not signer.verify("tok123", 1001, sig)


def test_tampered_token_id_fails():
    signer = HmacTokenSigner(b"secret-key")
    sig = signer.sign("tok123", 1000)
    assert not signer.verify("tokXXX", 1000, sig)


def test_wrong_key_fails():
    sig = HmacTokenSigner(b"key-a").sign("tok123", 1000)
    assert not HmacTokenSigner(b"key-b").verify("tok123", 1000, sig)
