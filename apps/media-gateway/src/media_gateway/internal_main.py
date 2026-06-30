"""Arranque del **plano interno** del media-gateway (wiring de producción). ADR-0017.

`uvicorn media_gateway.internal_main:app`. Misma imagen que el plano público; el Deployment K8s del
plano interno override-a el CMD a este módulo. Service privado (sin Ingress), IRSA/mTLS.
"""
from __future__ import annotations

import logging
import os

from .adapters.chained_audit_log import ChainedAuditLog
from .adapters.pg_grant_store import PgGrantStore
from .api.internal_app import create_internal_app
from .application.grant_service import GrantService
from .config import GatewayConfig
from .wiring import build_signer


def build_internal_app():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = GatewayConfig.from_env()
    store = PgGrantStore(cfg.grant_dsn)
    grants = GrantService(
        store=store,
        signer=build_signer(cfg),
        audit=ChainedAuditLog(cfg.audit_dsn),
        public_base_url=cfg.public_base_url,
    )
    # Bootstrap idempotente del ledger (CREATE TABLE IF NOT EXISTS). Se ejecuta al construir la app
    # del entrypoint de prod; los tests usan create_internal_app con fakes y no importan este módulo,
    # así que no conectan a PG.
    store.init_schema()
    return create_internal_app(grants)


app = build_internal_app()  # uvicorn media_gateway.internal_main:app


def main() -> None:
    import uvicorn
    uvicorn.run("media_gateway.internal_main:app", host="0.0.0.0", port=8081)


if __name__ == "__main__":
    main()
