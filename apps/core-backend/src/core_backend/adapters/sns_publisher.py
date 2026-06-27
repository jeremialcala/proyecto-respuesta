"""Publica report.ingested / state.changed en SNS (ADR-0012). `boto3` perezoso.

`topic` lógico → ARN configurado. Mapa simple para el MVP.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SnsPublisher:
    def __init__(self, topic_arns: dict[str, str], region: str) -> None:
        self._arns = topic_arns
        self._region = region
        self._client = None

    def _ensure(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("sns", region_name=self._region)
        return self._client

    def publish(self, topic: str, envelope: dict) -> None:
        arn = self._arns.get(topic)
        if not arn:
            raise ValueError(f"topic sin ARN configurado: {topic}")
        self._ensure().publish(
            TopicArn=arn, Message=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": envelope["event_type"]},
                "event_id": {"DataType": "String", "StringValue": envelope["event_id"]},
            })
        log.info("⇢ publicado %s event_id=%s → SNS %s", envelope["event_type"], envelope["event_id"], arn)
