"""Adaptador de ingestión AWS SQS — patrón cola+worker con long polling (ADR-0012).

Genérico: recibe un `handler(envelope)` y lo invoca por cada mensaje. Permite cablear varias colas
(p. ej. `report.ingested` y `face.disambiguation.resolved` → EnrollmentService) reusando el mismo
bucle. Entrega *at-least-once* → idempotencia por `event_id`/`disambiguation_id` (ADR-0011/0016). Los
mensajes inprocesables no se borran: tras `maxReceiveCount` la redrive policy los manda a la DLQ.
`boto3` se importa perezoso.
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

    def _ensure_client(self):
        if self._client is None:
            import boto3  # import perezoso
            self._client = boto3.client("sqs", region_name=self._region)
        return self._client

    def start(self) -> None:
        client = self._ensure_client()
        self._running = True
        log.info("escuchando %s en %s", self._name, self._queue_url)
        while self._running:
            resp = client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=self._max,
                WaitTimeSeconds=self._wait,
                MessageAttributeNames=["All"],
            )
            msgs = resp.get("Messages", [])
            if msgs:
                log.info("[%s] recibidos %d mensaje(s)", self._name, len(msgs))
            for msg in msgs:
                eid = "?"
                try:
                    envelope = json.loads(msg["Body"])
                    eid = envelope.get("event_id", "?")
                    log.info("[%s] → procesando event_id=%s event_type=%s",
                             self._name, eid, envelope.get("event_type", "?"))
                    self._handler(envelope)
                except Exception:
                    # No borrar → redrive a DLQ tras maxReceiveCount (ADR-0012). Falla visible.
                    log.exception("[%s] ✗ fallo event_id=%s → sin borrar (redrive a DLQ)",
                                  self._name, eid)
                    continue
                else:
                    client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=msg["ReceiptHandle"])
                    log.info("[%s] ✓ procesado event_id=%s → borrado", self._name, eid)

    def stop(self) -> None:
        self._running = False
