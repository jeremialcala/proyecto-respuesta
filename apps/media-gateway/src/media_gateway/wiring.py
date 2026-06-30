"""Selección de adaptadores por entorno (ADR-0014/0017). Default = producción (KMS/Meta).

En dev-local se conmuta a los fakes de `adapters/` por variables de entorno, igual que el vault-worker
usa `VAULT_CIPHER=passthrough`: así el media-gateway corre sin KMS ni rangos de Meta. Estos switches
**no** se setean en los manifiestos de prod → quedan en KMS/Meta.
"""
from __future__ import annotations

from .config import GatewayConfig


def build_signer(cfg: GatewayConfig):
    """TokenSigner: KMS (prod) o HMAC en proceso con secreto compartido (dev)."""
    if cfg.token_signer == "hmac":
        from .adapters.hmac_token_signer import HmacTokenSigner
        return HmacTokenSigner(cfg.hmac_shared_secret.encode())
    from .adapters.kms_token_signer import KmsTokenSigner
    return KmsTokenSigner(cfg.hmac_key_id, cfg.aws_region)


def build_cipher(cfg: GatewayConfig):
    """EnvelopeCipher: KMS unwrap+AES-GCM (prod) o passthrough para medios en claro (dev)."""
    if cfg.media_cipher == "passthrough":
        from .adapters.passthrough_cipher import PassthroughCipher
        return PassthroughCipher()
    from .adapters.kms_envelope_cipher import KmsEnvelopeCipher
    return KmsEnvelopeCipher(cfg.aws_region)


def build_allowlist(cfg: GatewayConfig):
    """FetcherAllowlist: rangos/UA de Meta (prod) o allow-all estático (dev)."""
    if cfg.fetcher_allowlist == "static":
        from .adapters.static_allowlist import StaticAllowlist
        return StaticAllowlist(allow_all=True)
    from .adapters.meta_fetcher_allowlist import MetaFetcherAllowlist
    return MetaFetcherAllowlist(cfg.meta_fetcher_cidrs, cfg.meta_fetcher_user_agents)
