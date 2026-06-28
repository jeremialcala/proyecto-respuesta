"""Arranque del **plano público** del media-gateway (wiring de producción). ADR-0017.

`uvicorn media_gateway.public_main:app`. Inyecta los adaptadores reales (Pg/KMS/S3/Redis/auditoría
encadenada). Es el único entrypoint expuesto (tras ALB+WAF).
"""
from __future__ import annotations

import logging
import os

from .adapters.chained_audit_log import ChainedAuditLog
from .adapters.kms_envelope_cipher import KmsEnvelopeCipher
from .adapters.kms_token_signer import KmsTokenSigner
from .adapters.meta_fetcher_allowlist import MetaFetcherAllowlist
from .adapters.pg_grant_store import PgGrantStore
from .adapters.redis_rate_limiter import RedisRateLimiter
from .adapters.s3_media_store import S3MediaStore
from .api.public_app import create_public_app
from .application.delivery_service import DeliveryService
from .config import GatewayConfig


def build_public_app():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = GatewayConfig.from_env()
    delivery = DeliveryService(
        grants=PgGrantStore(cfg.grant_dsn),
        signer=KmsTokenSigner(cfg.hmac_key_id, cfg.aws_region),
        allowlist=MetaFetcherAllowlist(cfg.meta_fetcher_cidrs, cfg.meta_fetcher_user_agents),
        limiter=RedisRateLimiter(cfg.redis_url, cfg.rate_max_hits, cfg.rate_window_seconds),
        media=S3MediaStore(cfg.aws_region),
        cipher=KmsEnvelopeCipher(cfg.aws_region),
        audit=ChainedAuditLog(cfg.audit_dsn),
    )
    return create_public_app(delivery)


app = build_public_app()  # uvicorn media_gateway.public_main:app


def main() -> None:
    import uvicorn
    uvicorn.run("media_gateway.public_main:app", host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
