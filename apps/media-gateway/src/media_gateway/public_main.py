"""Arranque del **plano público** del media-gateway (wiring de producción). ADR-0017.

`uvicorn media_gateway.public_main:app`. Inyecta los adaptadores reales (Pg/KMS/S3/Redis/auditoría
encadenada). Es el único entrypoint expuesto (tras ALB+WAF).
"""
from __future__ import annotations

import logging
import os

from .adapters.chained_audit_log import ChainedAuditLog
from .adapters.pg_grant_store import PgGrantStore
from .adapters.redis_rate_limiter import RedisRateLimiter
from .adapters.s3_media_store import S3MediaStore
from .api.public_app import create_public_app
from .application.delivery_service import DeliveryService
from .config import GatewayConfig
from .wiring import build_allowlist, build_cipher, build_signer


def build_public_app():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = GatewayConfig.from_env()
    store = PgGrantStore(cfg.grant_dsn)
    delivery = DeliveryService(
        grants=store,
        signer=build_signer(cfg),
        allowlist=build_allowlist(cfg),
        limiter=RedisRateLimiter(cfg.redis_url, cfg.rate_max_hits, cfg.rate_window_seconds),
        media=S3MediaStore(cfg.aws_region),
        cipher=build_cipher(cfg),
        audit=ChainedAuditLog(cfg.audit_dsn),
    )
    # Bootstrap idempotente del ledger (CREATE TABLE IF NOT EXISTS). Se ejecuta al construir la app
    # del entrypoint de prod; los tests usan create_public_app con fakes y no importan este módulo,
    # así que no conectan a PG.
    store.init_schema()
    return create_public_app(delivery)


app = build_public_app()  # uvicorn media_gateway.public_main:app


def main() -> None:
    import uvicorn
    uvicorn.run("media_gateway.public_main:app", host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
