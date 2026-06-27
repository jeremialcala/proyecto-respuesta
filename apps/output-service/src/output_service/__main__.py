"""Arranque del Servicio de Salida (wiring). outbound.reply → Graph API (texto/HSM)."""
from __future__ import annotations

import logging
import os

from .application.output_service import OutputService
from .adapters.graph_sender import GraphSender
from .adapters.noop_event_log import NoopEventLog
from .adapters.passthrough_cipher import PassthroughCipher
from .adapters.redis_window_store import RedisWindowStore
from .adapters.sqs_consumer import SqsConsumer
from .config import OutputConfig


def build_consumer(cfg: OutputConfig) -> SqsConsumer:
    service = OutputService(
        cfg,
        cipher=PassthroughCipher(),
        window=RedisWindowStore(cfg.redis_url),
        sender=GraphSender(cfg.graph_api_base, dry_run=cfg.dry_run),
        event_log=NoopEventLog(),
    )
    return SqsConsumer(cfg.input_queue_url, cfg.aws_region, service,
                       cfg.max_messages, cfg.wait_time_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    build_consumer(OutputConfig.from_env()).start()


if __name__ == "__main__":
    main()
