"""Arranque del Meta Handler (wiring). Consume meta.received, reparte a inbound.* (ADR-0005/0012)."""
from __future__ import annotations

import logging
import os

from .application.handler_service import HandlerService
from .adapters.jwe_cipher import PassthroughCipher
from .adapters.noop_event_log import NoopEventLog
from .adapters.redis_window_store import RedisWindowStore
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_inbound_publisher import SqsInboundPublisher
from .config import HandlerConfig


def build_consumer(cfg: HandlerConfig) -> SqsConsumer:
    publisher = SqsInboundPublisher(cfg.text_queue_url, cfg.media_queue_url, cfg.aws_region)
    window = RedisWindowStore(cfg.redis_url, cfg.window_ttl_seconds)
    service = HandlerService(cfg, publisher, PassthroughCipher(), NoopEventLog(), window)
    return SqsConsumer(cfg.input_queue_url, cfg.aws_region, service,
                       cfg.max_messages, cfg.wait_time_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    build_consumer(HandlerConfig.from_env()).start()


if __name__ == "__main__":
    main()
