"""Consume report.received y delega en el IntakeService (ADR-0011/0012). `boto3` perezoso."""
from __future__ import annotations

import json
import logging

from ..application.intake_service import IntakeService

log = logging.getLogger(__name__)


class SqsConsumer:
    def __init__(self, queue_url: str, region: str, service: IntakeService,
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
        log.info("escuchando report.received en %s", self._queue_url)
        while self._running:
            resp = client.receive_message(
                QueueUrl=self._queue_url, MaxNumberOfMessages=self._max,
                WaitTimeSeconds=self._wait, MessageAttributeNames=["All"])
            msgs = resp.get("Messages", [])
            if msgs:
                log.info("recibidos %d mensaje(s)", len(msgs))
            for m in msgs:
                eid = "?"
                try:
                    body = json.loads(m["Body"])
                    eid = body.get("event_id", "?")
                    log.info("→ procesando event_id=%s event_type=%s", eid, body.get("event_type", "?"))
                    self._service.handle(body)
                except Exception:
                    log.exception("✗ fallo event_id=%s → sin borrar (redrive a DLQ)", eid)
                    continue
                else:
                    client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=m["ReceiptHandle"])
                    log.info("✓ procesado event_id=%s → borrado", eid)

    def stop(self) -> None:
        self._running = False
