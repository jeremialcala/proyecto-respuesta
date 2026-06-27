"""Publicador del crudo a SQS `meta.received` (ADR-0005/0012). `boto3` se importa perezoso.

Idempotencia aguas abajo por `event_id` del sobre (entrega at-least-once). El cuerpo no lleva
biométricos (el binario no viaja por el webhook; solo el JSON crudo del mensaje).
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SqsRawPublisher:
    def __init__(self, queue_url: str, region: str) -> None:
        self._queue_url = queue_url
        self._region = region
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import boto3  # import perezoso
            self._client = boto3.client("sqs", region_name=self._region)
        return self._client

    def publish_raw(self, envelope: dict) -> None:
        client = self._ensure_client()
        client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": envelope["event_type"]},
                "event_id": {"DataType": "String", "StringValue": envelope["event_id"]},
            },
        )
        log.info("⇢ publicado meta.received event_id=%s → %s", envelope["event_id"], self._queue_url)
