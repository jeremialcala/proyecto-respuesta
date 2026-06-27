"""Publica media.stored en SNS (fan-out al motor de matching) — ADR-0012. `boto3` perezoso."""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SnsEventPublisher:
    def __init__(self, topic_arn: str, region: str) -> None:
        self._arn = topic_arn
        self._region = region
        self._client = None

    def _ensure(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("sns", region_name=self._region)
        return self._client

    def publish(self, envelope: dict) -> None:
        self._ensure().publish(
            TopicArn=self._arn,
            Message=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": envelope["event_type"]},
                "event_id": {"DataType": "String", "StringValue": envelope["event_id"]},
            },
        )
        log.info("⇢ publicado %s event_id=%s → SNS %s", envelope["event_type"], envelope["event_id"], self._arn)
