"""Consume inbound.text y delega en el ChatbotService (ADR-0001/0012). `boto3` perezoso."""
from __future__ import annotations

import json

from ..application.chatbot_service import ChatbotService


class SqsConsumer:
    def __init__(self, queue_url: str, region: str, service: ChatbotService,
                 max_messages: int = 10, wait_time_seconds: int = 20) -> None:
        self._queue_url = queue_url
        self._region = region
        self._service = service
        self._max = max_messages
        self._wait = wait_time_seconds
        self._client = None
        self._running = False

    def _ensure(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("sqs", region_name=self._region)
        return self._client

    def start(self) -> None:
        client = self._ensure()
        self._running = True
        while self._running:
            resp = client.receive_message(
                QueueUrl=self._queue_url, MaxNumberOfMessages=self._max,
                WaitTimeSeconds=self._wait, MessageAttributeNames=["All"])
            for m in resp.get("Messages", []):
                try:
                    self._service.handle(json.loads(m["Body"]))
                except Exception:
                    continue   # no borrar → DLQ por redrive
                else:
                    client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=m["ReceiptHandle"])

    def stop(self) -> None:
        self._running = False
