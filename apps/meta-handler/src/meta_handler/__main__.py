"""Arranque del Meta Handler (wiring). Consume meta.received, reparte a inbound.* (ADR-0005/0012)."""
from __future__ import annotations

from .application.handler_service import HandlerService
from .adapters.jwe_cipher import PassthroughCipher
from .adapters.noop_event_log import NoopEventLog
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_inbound_publisher import SqsInboundPublisher
from .config import HandlerConfig


def build_consumer(cfg: HandlerConfig) -> SqsConsumer:
    publisher = SqsInboundPublisher(cfg.text_queue_url, cfg.media_queue_url, cfg.aws_region)
    service = HandlerService(cfg, publisher, PassthroughCipher(), NoopEventLog())
    return SqsConsumer(cfg.input_queue_url, cfg.aws_region, service,
                       cfg.max_messages, cfg.wait_time_seconds)


def main() -> None:
    build_consumer(HandlerConfig.from_env()).start()


if __name__ == "__main__":
    main()
