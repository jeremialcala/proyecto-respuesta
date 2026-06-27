"""Arranque del Webhook Gateway (wiring). Uvicorn sirve la app FastAPI (ADR-0005/0012)."""
from __future__ import annotations

import logging
import os

from .api.app import create_app
from .application.ingest_service import IngestService
from .adapters.redis_idempotency import RedisIdempotencyStore
from .adapters.sqs_raw_publisher import SqsRawPublisher
from .config import GatewayConfig


def build_app():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = GatewayConfig.from_env()
    idem = RedisIdempotencyStore(cfg.redis_url, cfg.idempotency_ttl_seconds)
    publisher = SqsRawPublisher(cfg.raw_queue_url, cfg.aws_region)
    return create_app(IngestService(cfg, idem, publisher))


app = build_app()  # uvicorn webhook_gateway.__main__:app


def main() -> None:
    import uvicorn
    uvicorn.run("webhook_gateway.__main__:app", host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
