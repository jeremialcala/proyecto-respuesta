"""Caso de uso: enrolar el rostro del sujeto de un reporte y desambiguar multi-rostro (ADR-0016).

Consume dos eventos (ver `__main__`):
- `report.ingested`        → detecta rostros en la foto de referencia y ramifica por su número.
- `face.disambiguation.resolved` → enrola el rostro elegido por el reportante y purga el resto.

Minimización (A04): los embeddings/recortes de rostros NO elegidos nunca llegan al índice de largo
plazo; viven en el `PendingEnrollment` + recortes efímeros en la bóveda y se purgan al resolver o
expirar. Idempotencia (at-least-once, ADR-0012): `add_reference` es upsert por `entity_id`; un
`resolved` duplicado es no-op si el pendiente ya está `resolved`.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..config import QualityThresholds
from ..domain.models import FaceMap, PendingEnrollment, PendingFace
from .ports import (AnnIndex, EmbeddingStore, EventBus, FaceMapper, GrantRevoker, MediaGateway,
                    PendingEnrollmentStore)

log = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bbox_list(face: FaceMap | PendingFace):
    b = face.bbox
    return [b.x1, b.y1, b.x2, b.y2] if b is not None else None


def _reporter_fields(reporter: Optional[dict]) -> dict:
    """Campos de identidad del reportante para los eventos de feedback (ADR-0016)."""
    r = reporter or {}
    return {"bot_id": r.get("bot_id", ""), "channel": r.get("channel", ""),
            "contact_ref": r.get("contact_ref", "")}


class EnrollmentService:
    def __init__(
        self,
        face_mapper: FaceMapper,
        media: MediaGateway,
        store: EmbeddingStore,
        index: AnnIndex,
        pending: PendingEnrollmentStore,
        bus: EventBus,
        quality: QualityThresholds | None = None,
        *,
        grant_revoker: GrantRevoker | None = None,
        pending_ttl_seconds: int = 86400,
        crop_ttl_seconds: int = 86400,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        id_fn: Callable[[], str] = lambda: f"dis_{uuid.uuid4().hex}",
    ) -> None:
        self._fm = face_mapper
        self._media = media
        self._store = store
        self._index = index
        self._pending = pending
        self._bus = bus
        self._q = quality or QualityThresholds()
        self._revoker = grant_revoker   # revoca las concesiones del media-gateway al purgar (ADR-0016 §6)
        self._pending_ttl = pending_ttl_seconds
        self._crop_ttl = crop_ttl_seconds
        self._now = now_fn
        self._new_id = id_fn

    # --- helpers ---
    def _presentable(self, face: FaceMap) -> bool:
        """Filtra caras de fondo diminutas/borrosas antes de contar (no preguntar por ruido)."""
        if face.quality.size_px < self._q.min_size_px:
            return False
        bv = face.quality.blur_var
        if not math.isnan(bv) and bv < self._q.min_blur_var:
            return False
        return True

    def _enroll(self, entity_id: str, face: FaceMap, report_id: Optional[str],
                source: str, reporter: Optional[dict] = None) -> None:
        self._store.add_reference(entity_id, face.embedding)   # upsert por entity_id (idempotente)
        self._index.rebuild_from(self._store)                  # refresca el ANN desde pgvector
        payload = {
            "entity_id": entity_id,
            "report_id": report_id,
            "face_quality": {"size_px": face.quality.size_px, "blur_var": face.quality.blur_var},
            "det_score": face.det_score,
            "source": source,
        }
        payload.update(_reporter_fields(reporter))   # identidad para avisar al reportante (ADR-0016)
        self._bus.publish("entity.enrolled", payload)
        log.info("✓ enrolado entity_id=%s (source=%s)", entity_id, source)

    def _fail(self, entity_id: Optional[str], report_id: Optional[str], reason: str,
              reporter: Optional[dict] = None) -> None:
        payload = {"entity_id": entity_id, "report_id": report_id, "reason": reason}
        payload.update(_reporter_fields(reporter))
        self._bus.publish("enrollment.failed", payload)
        log.info("✗ enrolamiento fallido entity_id=%s reason=%s", entity_id, reason)

    def _purge(self, pending: PendingEnrollment, crop_refs: list[str]) -> None:
        """Purga los recortes de la bóveda y revoca las concesiones que sirvieron esas miniaturas.

        La purga del recorte (PII real) es la garantía; la revocación de la concesión del media-gateway
        (ADR-0017) es best-effort —su TTL corto es el respaldo— para no bloquear el enrolamiento.
        """
        self._media.delete_crops(crop_refs)
        if self._revoker is not None:
            self._revoker.revoke_grants(report_id=pending.report_id, media_refs=crop_refs)

    # --- report.ingested ---
    def on_report_ingested(self, envelope: dict) -> None:
        p = envelope.get("payload", {}) or {}
        entity_id = p.get("entity_id")
        report_id = p.get("report_id")
        media_ref = p.get("media_ref")
        conversation_key = p.get("conversation_key")
        reporter = {"bot_id": p.get("bot_id", ""), "channel": p.get("channel", ""),
                    "contact_ref": p.get("contact_ref", "")}
        if not entity_id or not media_ref:
            log.warning("report.ingested sin entity_id/media_ref; se ignora (event_id=%s)",
                        envelope.get("event_id"))
            return

        image = self._media.fetch(media_ref)
        faces = [f for f in self._fm.map_image(image) if self._presentable(f)]

        if not faces:
            self._fail(entity_id, report_id, "no_face", reporter)
            return
        if len(faces) == 1:
            self._enroll(entity_id, faces[0], report_id, "report.ingested", reporter)
            return

        # ≥2 rostros: NO enrola; recorta, guarda efímero y pregunta al reportante.
        crops = self._fm.crop_faces(image, [f.bbox for f in faces])  # type: ignore[misc]
        crop_refs = self._media.store_crops(crops, self._crop_ttl)
        now = self._now()
        pending_faces = tuple(
            PendingFace(index=i, embedding=f.embedding, bbox=f.bbox, det_score=f.det_score,
                        crop_ref=(crop_refs[i] if i < len(crop_refs) else None))
            for i, f in enumerate(faces)
        )
        pending = PendingEnrollment(
            disambiguation_id=self._new_id(),
            entity_id=entity_id, report_id=report_id, faces=pending_faces,
            conversation_key=conversation_key,
            created_at=_iso(now), expires_at=_iso(now + timedelta(seconds=self._pending_ttl)),
            reporter=reporter,
        )
        self._pending.save(pending)
        req = {
            "disambiguation_id": pending.disambiguation_id,
            "entity_id": entity_id, "report_id": report_id,
            "conversation_key": conversation_key, "expires_at": pending.expires_at,
            "faces": [
                {"index": pf.index, "crop_ref": pf.crop_ref,
                 "bbox": _bbox_list(pf), "det_score": pf.det_score}
                for pf in pending_faces
            ],
        }
        req.update(_reporter_fields(reporter))   # identidad para que el chatbot pregunte (ADR-0016)
        self._bus.publish("face.disambiguation.requested", req)
        log.info("? desambiguación solicitada dis=%s entity_id=%s rostros=%d",
                 pending.disambiguation_id, entity_id, len(pending_faces))

    # --- face.disambiguation.resolved ---
    def on_disambiguation_resolved(self, envelope: dict) -> None:
        p = envelope.get("payload", {}) or {}
        disambiguation_id = p.get("disambiguation_id")
        if not disambiguation_id:
            log.warning("disambiguation.resolved sin disambiguation_id; se ignora")
            return

        pending = self._pending.get(disambiguation_id)
        if pending is None:
            # Nunca existió o ya fue purgado por expiración → pide reenviar la foto.
            self._fail(None, None, "expired", None)
            return
        if pending.status == "resolved":
            return  # idempotencia: resolved duplicado es no-op

        all_crops = [f.crop_ref for f in pending.faces if f.crop_ref]
        reporter = pending.reporter

        # Expirado: purga recortes y responde expired.
        if self._iso_now() > pending.expires_at:
            self._purge(pending, all_crops)
            self._pending.mark_resolved(disambiguation_id)
            self._fail(pending.entity_id, pending.report_id, "expired", reporter)
            return

        # El sujeto no está en la foto → purga todo y pide otra.
        if p.get("action") == "none_of_these":
            self._purge(pending, all_crops)
            self._pending.mark_resolved(disambiguation_id)
            self._fail(pending.entity_id, pending.report_id, "no_subject_in_photo", reporter)
            return

        selected = p.get("selected_index")
        if not isinstance(selected, int) or not (0 <= selected < len(pending.faces)):
            # Índice inválido: no enrola ni purga (permite corregir hasta el TTL).
            self._fail(pending.entity_id, pending.report_id, "invalid_selection", reporter)
            return

        chosen = pending.faces[selected]
        self._enroll(
            pending.entity_id,
            FaceMap(embedding=chosen.embedding, quality=_zero_quality(),
                    bbox=chosen.bbox, det_score=chosen.det_score),
            pending.report_id, "face.disambiguation.resolved", reporter,
        )
        self._purge(pending, all_crops)                # minimización: purga recortes + revoca concesiones
        self._pending.mark_resolved(disambiguation_id)

    def _iso_now(self) -> str:
        return _iso(self._now())


def _zero_quality():
    """Calidad neutra para el rostro ya elegido (su calidad se evaluó al detectar)."""
    from ..domain.models import FaceQuality
    return FaceQuality(size_px=0, blur_var=float("nan"), yaw=0.0, pitch=0.0)
