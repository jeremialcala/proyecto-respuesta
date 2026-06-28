"""Cliente petición-respuesta sobre SQS/SNS hacia el plano de inferencia (ADR-0019). `boto3` perezoso.

Publica `face.extract.requested` (`{job_id, image_b64}`) en el topic de extracción y hace long-poll de
su **cola de respuesta** (suscrita al topic `face.embedded`), casando por `job_id` y borrando solo el
mensaje propio. Si no llega antes del timeout, lanza `TimeoutError`: el handler SQS aguas arriba no
borra su mensaje → redrive/reintento, idempotente por `event_id` (ADR-0018). En tránsito viaja la cara
mínima (no la foto original completa cuando ya hubo pre-recorte); el nodo solo devuelve vectores.

Nota de operación (TODO, decisión abierta del ADR-0019): el lifecycle de la cola de respuesta por pod
(alta/baja, suscripción al topic) lo gestiona la IaC; aquí se consume una `reply_queue_url` ya provista.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid

from ..application.events import build_envelope

log = logging.getLogger(__name__)


class SqsRequestReplyClient:
    def __init__(self, extract_topic_arn: str, reply_queue_url: str, region: str,
                 producer: str = "matching-worker", poll_wait_seconds: int = 5) -> None:
        self._topic = extract_topic_arn
        self._reply_queue = reply_queue_url
        self._region = region
        self._producer = producer
        self._wait = poll_wait_seconds
        self._sns = None
        self._sqs = None

    def _ensure(self):
        if self._sns is None:
            import boto3  # import perezoso
            self._sns = boto3.client("sns", region_name=self._region)
            self._sqs = boto3.client("sqs", region_name=self._region)
        return self._sns, self._sqs

    def request(self, image_bytes: bytes, *, timeout: float) -> list[dict]:
        sns, sqs = self._ensure()
        job_id = uuid.uuid4().hex
        payload = {"job_id": job_id, "image_b64": base64.b64encode(image_bytes).decode("ascii")}
        envelope = build_envelope("face.extract.requested", payload, self._producer)
        sns.publish(
            TopicArn=self._topic,
            Message=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": "face.extract.requested"},
                "job_id": {"DataType": "String", "StringValue": job_id},
            },
        )
        log.info("⇢ face.extract.requested job_id=%s → SNS (esperando respuesta)", job_id)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = sqs.receive_message(
                QueueUrl=self._reply_queue,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=self._wait,
                MessageAttributeNames=["All"],
            )
            for msg in resp.get("Messages", []):
                try:
                    body = json.loads(msg["Body"])
                    # SNS→SQS envuelve el sobre dentro de "Message"; soportar ambas formas.
                    inner = json.loads(body["Message"]) if "Message" in body else body
                    p = inner.get("payload", {}) or {}
                except Exception:
                    continue
                if p.get("job_id") == job_id:
                    sqs.delete_message(QueueUrl=self._reply_queue, ReceiptHandle=msg["ReceiptHandle"])
                    return p.get("faces", [])
                # Respuesta de otro job (cola compartida por fan-out): no borrar, dejar que expire/lo tome su dueño.
        raise TimeoutError(f"face.embedded no llegó para job_id={job_id} en {timeout}s")
