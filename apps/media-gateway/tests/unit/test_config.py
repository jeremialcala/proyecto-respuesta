"""Config 12-factor y selección de adaptadores por entorno (ADR-0014/0017)."""
from media_gateway.adapters.hmac_token_signer import HmacTokenSigner
from media_gateway.adapters.passthrough_cipher import PassthroughCipher
from media_gateway.adapters.static_allowlist import StaticAllowlist
from media_gateway.config import GatewayConfig
from media_gateway.wiring import build_allowlist, build_cipher, build_signer


def test_defaults_are_production_adapters():
    # Sin env, los switches quedan en KMS/Meta (no se regresa el comportamiento prod).
    cfg = GatewayConfig()
    assert cfg.token_signer == "kms"
    assert cfg.media_cipher == "kms"
    assert cfg.fetcher_allowlist == "meta"


def test_from_env_parses_dev_switches(monkeypatch):
    monkeypatch.setenv("TOKEN_SIGNER", "hmac")
    monkeypatch.setenv("HMAC_SHARED_SECRET", "dev-secret")
    monkeypatch.setenv("MEDIA_CIPHER", "passthrough")
    monkeypatch.setenv("FETCHER_ALLOWLIST", "static")
    cfg = GatewayConfig.from_env()
    assert cfg.token_signer == "hmac"
    assert cfg.hmac_shared_secret == "dev-secret"
    assert cfg.media_cipher == "passthrough"
    assert cfg.fetcher_allowlist == "static"


def test_wiring_selects_dev_fakes_without_kms():
    # Construir los adaptadores dev no debe tocar KMS/AWS (todo en proceso).
    cfg = GatewayConfig(token_signer="hmac", hmac_shared_secret="s",
                        media_cipher="passthrough", fetcher_allowlist="static")
    assert isinstance(build_signer(cfg), HmacTokenSigner)
    assert isinstance(build_cipher(cfg), PassthroughCipher)
    assert isinstance(build_allowlist(cfg), StaticAllowlist)


def test_dev_signer_round_trips_with_shared_secret():
    # El interno firma y el público (mismo secreto) verifica → la URL es válida entre planos.
    cfg = GatewayConfig(token_signer="hmac", hmac_shared_secret="shared")
    signer = build_signer(cfg)
    sig = signer.sign("tok", 9999999999)
    assert signer.verify("tok", 9999999999, sig)
