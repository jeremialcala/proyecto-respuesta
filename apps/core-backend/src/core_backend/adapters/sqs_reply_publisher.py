"""Publica outbound.reply en la cola SQS del servicio de salida (acuse al reportante, ADR-0020 RF-16).

`boto3` perezoso. No-op si no hay cola configurada (dev/tests sin canal de salida).
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SqsReplyPublisher:
    def __init__(self, reply_queue_url: str, region: str) -> None:
        self._url = reply_queue_url
        self._region = region
        self._client = None

    def _ensure(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("sqs", region_name=self._region)
        return self._client

    def publish_reply(self, envelope: dict) -> None:
        if not self._url:
            return
        self._ensure().send_message(
            QueueUrl=self._url, MessageBody=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": envelope["event_type"]},
                "event_id": {"DataType": "String", "StringValue": envelope["event_id"]},
            })
        log.info("⇢ publicado outbound.reply (acuse) event_id=%s → %s", envelope["event_id"], self._url)
