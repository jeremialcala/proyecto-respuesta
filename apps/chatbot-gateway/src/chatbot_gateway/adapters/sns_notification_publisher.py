"""Publica notification.sent en un topic SNS para auditoría/observabilidad (ADR-0020 RF-22, ADR-0011).

`boto3` perezoso. No-op si no hay topic configurado (dev/tests sin el ARN).
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SnsNotificationPublisher:
    def __init__(self, topic_arn: str, region: str) -> None:
        self._arn = topic_arn
        self._region = region
        self._client = None

    def _ensure(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("sns", region_name=self._region)
        return self._client

    def publish_notification(self, envelope: dict) -> None:
        if not self._arn:
            return
        self._ensure().publish(
            TopicArn=self._arn, Message=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": envelope["event_type"]},
            })
        log.info("⇢ publicado notification.sent purpose=%s → %s",
                 (envelope.get("payload") or {}).get("purpose"), self._arn)
