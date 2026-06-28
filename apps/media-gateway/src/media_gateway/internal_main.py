"""Arranque del **plano interno** del media-gateway (wiring de producción). ADR-0017.

`uvicorn media_gateway.internal_main:app`. Misma imagen que el plano público; el Deployment K8s del
plano interno override-a el CMD a este módulo. Service privado (sin Ingress), IRSA/mTLS.
"""
from __future__ import annotations

import logging
import os

from .adapters.chained_audit_log import ChainedAuditLog
from .adapters.kms_token_signer import KmsTokenSigner
from .adapters.pg_grant_store import PgGrantStore
from .api.internal_app import create_internal_app
from .application.grant_service import GrantService
from .config import GatewayConfig


def build_internal_app():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = GatewayConfig.from_env()
    grants = GrantService(
        store=PgGrantStore(cfg.grant_dsn),
        signer=KmsTokenSigner(cfg.hmac_key_id, cfg.aws_region),
        audit=ChainedAuditLog(cfg.audit_dsn),
        public_base_url=cfg.public_base_url,
    )
    return create_internal_app(grants)


app = build_internal_app()  # uvicorn media_gateway.internal_main:app


def main() -> None:
    import uvicorn
    uvicorn.run("media_gateway.internal_main:app", host="0.0.0.0", port=8081)


if __name__ == "__main__":
    main()
