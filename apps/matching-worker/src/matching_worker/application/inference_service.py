"""Caso de uso del plano de inferencia (ADR-0019): imagen → embeddings, efímero y sin estado.

Consume `face.extract.requested` (la imagen mínima necesaria), corre el pipeline ArcFace y publica
`face.embedded` con **solo los vectores 512-d** + geometría por rostro. NO persiste nada: ni la imagen,
ni los embeddings (la galería/Vault/pgvector viven en-región). Diseñado para correr en GPU dedicada
(ADR-0018), incluido un nodo de burst on-demand verificado (vast.ai Secure Cloud) que devuelve el vector
y descarta la imagen al terminar la instancia. Puro respecto a infra: recibe `mapper` y `bus` por
constructor; `boto3`/InsightFace quedan en los adaptadores (lazy).
"""
from __future__ import annotations

import base64
import logging

from .face_codec import face_to_dict
from .ports import EventBus, FaceMapper

log = logging.getLogger(__name__)


class InferenceService:
    def __init__(self, mapper: FaceMapper, bus: EventBus) -> None:
        self._mapper = mapper
        self._bus = bus

    def on_extract_requested(self, envelope: dict) -> None:
        p = envelope.get("payload", {}) or {}
        job_id = p.get("job_id")
        image_b64 = p.get("image_b64")
        if not job_id or not image_b64:
            log.warning("face.extract.requested sin job_id/image_b64; se ignora (event_id=%s)",
                        envelope.get("event_id"))
            return

        try:
            image = base64.b64decode(image_b64)
        except Exception:
            image = b""
        faces = self._mapper.map_image(image) if image else []

        # Solo-vector: ninguna imagen viaja de vuelta ni se persiste (minimización A04, ADR-0019 §4).
        self._bus.publish("face.embedded", {
            "job_id": job_id,
            "faces": [face_to_dict(f) for f in faces],
        })
        log.info("⇢ face.embedded job_id=%s rostros=%d", job_id, len(faces))
