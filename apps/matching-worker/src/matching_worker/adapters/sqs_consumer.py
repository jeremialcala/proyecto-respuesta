"""Adaptador de ingestión AWS SQS — consume `report.ingested`, ejecuta el matching (ADR-0012).

Patrón cola+worker con long polling. Entrega *at-least-once* → idempotencia por `event_id`
(ADR-0011). Los mensajes inprocesables no se borran: tras `maxReceiveCount` la **redrive policy**
los manda a la DLQ (ADR-0005/0012), donde el Gestor de DLQ los audita. `boto3` se importa perezoso.
"""
from __future__ import annotations

import json

from ..application.matching_service import MatchingService, ProbeContext


class SqsConsumer:
    def __init__(self, queue_url: str, region: str, service: MatchingService,
                 max_messages: int = 10, wait_time_seconds: int = 20) -> None:
        self._queue_url = queue_url
        self._region = region
        self._service = service
        self._max = max_messages
        self._wait = wait_time_seconds
        self._client = None
        self._running = False

    def _ensure_client(self):
        if self._client is None:
            import boto3  # import perezoso
            self._client = boto3.client("sqs", region_name=self._region)
        return self._client

    @staticmethod
    def _to_probe(envelope: dict) -> ProbeContext:
        """Construye el ProbeContext desde el payload de `report.ingested` (ADR-0011).

        El probe necesita el embedding 512-d. Si el payload lo trae inline (`probe_embedding`),
        se usa; si trae `media_ref`, el wiring debe resolverlo con el FaceMapper (TODO fase-03).
        """
        payload = envelope.get("payload", {})
        emb = payload.get("probe_embedding")
        if emb is None:
            raise ValueError("report.ingested sin probe_embedding (resolver media_ref con FaceMapper — fase 03)")
        return ProbeContext(
            embedding=tuple(emb),
            report_id=payload.get("report_id"),
            is_minor=bool(payload.get("is_minor", False)),
            age_gap_years=float(payload.get("age_gap_years", 0.0)),
        )

    def _handle(self, body: str) -> None:
        envelope = json.loads(body)
        self._service.resolve(self._to_probe(envelope))

    def start(self) -> None:
        client = self._ensure_client()
        self._running = True
        while self._running:
            resp = client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=self._max,
                WaitTimeSeconds=self._wait,
                MessageAttributeNames=["All"],
            )
            for msg in resp.get("Messages", []):
                try:
                    self._handle(msg["Body"])
                except Exception:
                    # No borrar → redrive a DLQ tras maxReceiveCount (ADR-0012). Falla visible.
                    continue
                else:
                    client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=msg["ReceiptHandle"])

    def stop(self) -> None:
        self._running = False
