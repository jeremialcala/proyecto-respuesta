"""Adaptador AMQP: consume `report.ingested`, ejecuta el matching, publica `candidate.generated`.

Esqueleto (fase 03): pika BlockingConnection; el patrón cola+worker absorbe picos (ADR-0001).
"""
from __future__ import annotations

from ..application.matching_service import MatchingService


class AmqpConsumer:
    def __init__(self, amqp_url: str, service: MatchingService) -> None:
        self._amqp_url = amqp_url
        self._service = service
        # TODO(fase-03): pika.BlockingConnection + declare queue `report.ingested`

    def start(self) -> None:
        raise NotImplementedError("TODO(fase-03): consumir report.ingested y publicar candidatos")

    def publish(self, event: str, payload: dict) -> None:
        raise NotImplementedError("TODO(fase-03): publicar evento en AMQP")
