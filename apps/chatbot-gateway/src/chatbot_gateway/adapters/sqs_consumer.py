"""Consumidor SQS genérico (cola+worker, long polling) — ADR-0012. `boto3` perezoso.

Recibe un `handler(envelope)` y lo invoca por mensaje, permitiendo cablear varias colas hacia el
ChatbotService: `inbound.text` (conversación), `entity.enrolled` y `enrollment.failed` (feedback de
la foto al reportante, ADR-0016). Entrega *at-least-once* → idempotencia; los inprocesables no se
borran (redrive a DLQ).
"""
from __future__ import annotations

import json
import logging
from typing import Callable

log = logging.getLogger(__name__)


class SqsConsumer:
    def __init__(self, queue_url: str, region: str, handler: Callable[[dict], None],
                 max_messages: int = 10, wait_time_seconds: int = 20, name: str = "") -> None:
        self._queue_url = queue_url
        self._region = region
        self._handler = handler
        self._max = max_messages
        self._wait = wait_time_seconds
        self._name = name or queue_url.rsplit("/", 1)[-1]
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
        log.info("escuchando %s en %s", self._name, self._queue_url)
        while self._running:
            resp = client.receive_message(
                QueueUrl=self._queue_url, MaxNumberOfMessages=self._max,
                WaitTimeSeconds=self._wait, MessageAttributeNames=["All"])
            msgs = resp.get("Messages", [])
            if msgs:
                log.info("[%s] recibidos %d mensaje(s)", self._name, len(msgs))
            for m in msgs:
                eid = "?"
                try:
                    body = json.loads(m["Body"])
                    eid = body.get("event_id", "?")
                    log.info("[%s] → procesando event_id=%s event_type=%s",
                             self._name, eid, body.get("event_type", "?"))
                    self._handler(body)
                except Exception:
                    log.exception("[%s] ✗ fallo event_id=%s → sin borrar (redrive a DLQ)",
                                  self._name, eid)
                    continue   # no borrar → DLQ por redrive
                else:
                    client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=m["ReceiptHandle"])
                    log.info("[%s] ✓ procesado event_id=%s → borrado", self._name, eid)

    def stop(self) -> None:
        self._running = False
