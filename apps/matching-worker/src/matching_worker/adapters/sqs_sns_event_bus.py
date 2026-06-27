"""Adaptador de publicación de eventos sobre AWS SNS (fan-out) — ADR-0012.

Envuelve cada payload en el **sobre estándar** (ADR-0011, `application.events.build_envelope`) y lo
publica en un topic SNS. Los suscriptores SQS por consumidor reciben el fan-out. `boto3` se importa
de forma perezosa. Para cuerpos con PII/biométrico, cifrar en JWE antes de publicar (ADR-0012).
"""
from __future__ import annotations

import json
import logging

from ..application.events import build_envelope

log = logging.getLogger(__name__)


class SnsEventBus:
    def __init__(self, topic_arn: str, region: str, producer: str = "matching-worker") -> None:
        self._topic_arn = topic_arn
        self._region = region
        self._producer = producer
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import boto3  # import perezoso
            self._client = boto3.client("sns", region_name=self._region)
        return self._client

    def publish(self, event: str, payload: dict) -> None:
        envelope = build_envelope(event, payload, self._producer)
        client = self._ensure_client()
        client.publish(
            TopicArn=self._topic_arn,
            Message=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": event},
                "event_id": {"DataType": "String", "StringValue": envelope["event_id"]},
            },
        )
        log.info("⇢ publicado %s event_id=%s → SNS %s", event, envelope["event_id"], self._topic_arn)
