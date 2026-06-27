"""Arranque de la Pasarela de Chatbot (wiring). inbound.text → contexto+rieles+LLM → outbound.reply/report.received.

Además consume el feedback de enrolamiento (ADR-0016): `entity.enrolled` (avisa "reporte completo") y
`enrollment.failed` (guía a reenviar la foto), cada uno en su propio consumidor.
"""
from __future__ import annotations

import logging
import os
import threading

from .application.chatbot_service import ChatbotService
from .adapters.memory_conversation_store import MemoryConversationStore
from .adapters.noop_event_log import NoopEventLog
from .adapters.ollama_embedder import NullEmbedder, OllamaEmbedder
from .adapters.ollama_llm import OllamaLlmClient
from .adapters.passthrough_cipher import PassthroughCipher
from .adapters.sqs_consumer import SqsConsumer
from .adapters.sqs_publisher import SqsPublisher
from .config import ChatbotConfig

log = logging.getLogger(__name__)


def build_service(cfg: ChatbotConfig, pub) -> ChatbotService:
    # Memoria de conversación: Postgres+pgvector si hay DSN; si no, en memoria (dev/tests) — ADR-0015.
    if cfg.pgvector_dsn:
        from .adapters.pg_conversation_store import PgConversationStore
        store = PgConversationStore(cfg.pgvector_dsn, cfg.embed_dim)
        store.init_schema()
        log.info("ConversationStore: Postgres+pgvector (dim=%s)", cfg.embed_dim)
    else:
        store = MemoryConversationStore()
        log.info("ConversationStore: en memoria (sin PGVECTOR_DSN)")

    # Embeddings: Ollama si hay modelo configurado; si no, deshabilitados (solo ventana reciente).
    embedder = OllamaEmbedder(cfg.ollama_url, cfg.embed_model) if cfg.embed_model else NullEmbedder()

    return ChatbotService(
        cfg,
        cipher=PassthroughCipher(),
        llm=OllamaLlmClient(cfg.ollama_url, cfg.llm_model,
                            timeout=cfg.ollama_timeout, keep_alive=cfg.ollama_keep_alive),
        reply_pub=pub, report_pub=pub, event_log=NoopEventLog(),
        conversations=store, embedder=embedder,
    )


def build_consumers(cfg: ChatbotConfig, service: ChatbotService) -> list[SqsConsumer]:
    consumers = [
        SqsConsumer(cfg.input_queue_url, cfg.aws_region, service.handle,
                    cfg.max_messages, cfg.wait_time_seconds, name="inbound.text"),
    ]
    if cfg.entity_enrolled_queue_url:
        consumers.append(
            SqsConsumer(cfg.entity_enrolled_queue_url, cfg.aws_region, service.on_entity_enrolled,
                        cfg.max_messages, cfg.wait_time_seconds, name="entity.enrolled"))
    if cfg.enrollment_failed_queue_url:
        consumers.append(
            SqsConsumer(cfg.enrollment_failed_queue_url, cfg.aws_region, service.on_enrollment_failed,
                        cfg.max_messages, cfg.wait_time_seconds, name="enrollment.failed"))
    return consumers


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = ChatbotConfig.from_env()
    pub = SqsPublisher(cfg.reply_queue_url, cfg.report_queue_url, cfg.aws_region)
    service = build_service(cfg, pub)
    consumers = build_consumers(cfg, service)
    threads = [threading.Thread(target=c.start, name=c._name, daemon=True) for c in consumers]
    for t in threads:
        t.start()
    log.info("chatbot-gateway consumidores arriba: %s", ", ".join(c._name for c in consumers))
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
