"""Configuración del media-gateway (12-factor). ADR-0017 (ledger PG, KMS, S3, Redis, allowlist Meta).

Región São Paulo por defecto (ADR-0006). Los secretos (DSN, claves KMS) llegan por entorno/IRSA en
EKS (ADR-0014). El allowlist de fetchers de Meta se mantiene por config (ADR-0017 §Pendiente).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GatewayConfig:
    aws_region: str = "sa-east-1"                         # ADR-0006
    grant_dsn: str = ""                                   # ledger de concesiones (Postgres)
    audit_dsn: str = ""                                   # auditoría encadenada (Postgres, ADR-0007)
    redis_url: str = "redis://localhost:6379/0"           # rate-limit
    public_base_url: str = "https://media.respuesta.example"  # base de la URL firmada
    hmac_key_id: str = ""                                  # clave KMS del HMAC del token (ADR-0008)
    # Selección de adaptadores por entorno (defaults = producción). En dev-local se conmutan a los
    # fakes de `adapters/` para correr sin KMS, igual que `VAULT_CIPHER=passthrough` del vault-worker.
    token_signer: str = "kms"                             # kms (prod) | hmac (dev, HMAC compartido)
    hmac_shared_secret: str = ""                          # solo token_signer=hmac (dev)
    media_cipher: str = "kms"                             # kms (prod) | passthrough (dev, medios en claro)
    fetcher_allowlist: str = "meta"                       # meta (prod, rangos/UA) | static (dev, allow-all)
    # Rate-limit (ventana fija por token).
    rate_max_hits: int = 60
    rate_window_seconds: int = 60
    # Allowlist de fetchers de Meta (cambia; mantener por config — ADR-0017 §Pendiente).
    meta_fetcher_cidrs: tuple[str, ...] = field(default_factory=tuple)
    meta_fetcher_user_agents: tuple[str, ...] = ("facebookexternalhit", "whatsapp")

    @staticmethod
    def from_env() -> "GatewayConfig":
        cidrs = tuple(c.strip() for c in os.getenv("META_FETCHER_CIDRS", "").split(",") if c.strip())
        uas = tuple(u.strip() for u in os.getenv("META_FETCHER_USER_AGENTS", "").split(",") if u.strip())
        return GatewayConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            grant_dsn=os.getenv("GRANT_DSN", ""),
            audit_dsn=os.getenv("AUDIT_DSN", os.getenv("GRANT_DSN", "")),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "https://media.respuesta.example"),
            hmac_key_id=os.getenv("HMAC_KEY_ID", ""),
            token_signer=os.getenv("TOKEN_SIGNER", "kms"),
            hmac_shared_secret=os.getenv("HMAC_SHARED_SECRET", ""),
            media_cipher=os.getenv("MEDIA_CIPHER", "kms"),
            fetcher_allowlist=os.getenv("FETCHER_ALLOWLIST", "meta"),
            rate_max_hits=int(os.getenv("RATE_MAX_HITS", "60")),
            rate_window_seconds=int(os.getenv("RATE_WINDOW_SECONDS", "60")),
            meta_fetcher_cidrs=cidrs,
            meta_fetcher_user_agents=uas or ("facebookexternalhit", "whatsapp"),
        )
