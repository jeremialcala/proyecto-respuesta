"""Publica a las colas inbound.text / inbound.media en SQS (ADR-0012). `boto3` perezoso."""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SqsInboundPublisher:
    def __init__(self, text_queue_url: str, media_queue_url: str, region: str) -> None:
        self._text_url = text_queue_url
        self._media_url = media_queue_url
        self._region = region
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("sqs", region_name=self._region)
        return self._client

    def _send(self, url: str, envelope: dict) -> None:
        self._ensure_client().send_message(
            QueueUrl=url,
            MessageBody=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": envelope["event_type"]},
                "event_id": {"DataType": "String", "StringValue": envelope["event_id"]},
            },
        )
        log.info("⇢ publicado %s event_id=%s → %s", envelope["event_type"], envelope["event_id"], url)

    def publish_text(self, envelope: dict) -> None:
        self._send(self._text_url, envelope)

    def publish_media(self, envelope: dict) -> None:
        self._send(self._media_url, envelope)
