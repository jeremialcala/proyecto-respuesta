"""Arranque de la Pasarela de Chatbot (wiring). inbound.text → rieles+LLM → outbound.reply/report.received."""
from __future__ import annotations

import logging
import os

from .application.chatbot_service import ChatbotService
from .adapters.noop_event_log import NoopEventLog
from .adapters.ollama_llm import OllamaLlmClient
from .adapters.passthrough_cipher import PassthroughCipher
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_publisher import SqsPublisher
from .config import ChatbotConfig


def build_consumer(cfg: ChatbotConfig) -> SqsConsumer:
    pub = SqsPublisher(cfg.reply_queue_url, cfg.report_queue_url, cfg.aws_region)
    service = ChatbotService(
        cfg,
        cipher=PassthroughCipher(),
        llm=OllamaLlmClient(cfg.ollama_url, cfg.llm_model),
        reply_pub=pub, report_pub=pub, event_log=NoopEventLog(),
    )
    return SqsConsumer(cfg.input_queue_url, cfg.aws_region, service,
                       cfg.max_messages, cfg.wait_time_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    build_consumer(ChatbotConfig.from_env()).start()


if __name__ == "__main__":
    main()
