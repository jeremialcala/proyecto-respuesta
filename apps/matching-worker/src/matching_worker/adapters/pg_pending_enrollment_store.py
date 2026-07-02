"""PendingEnrollmentStore sobre Postgres (ADR-0016). `psycopg` perezoso, autocommit.

Las desambiguaciones en curso se guardan con su lista de rostros (jsonb) y un `expires_at` (TTL).
`purge_expired` borra las vencidas (job programado) para no retener biometría de terceros (A04).
Los timestamps se guardan como texto ISO-8601 'Z' para round-trip exacto con el dominio.
"""
from __future__ import annotations

import json
from typing import Optional

from ..domain.models import BBox, PendingEnrollment, PendingFace

_DDL = """
CREATE TABLE IF NOT EXISTS pending_enrollments (
    disambiguation_id text PRIMARY KEY,
    entity_id         text NOT NULL,
    report_id         text,
    conversation_key  text,
    faces             jsonb NOT NULL,
    reporter          jsonb,
    status            text NOT NULL DEFAULT 'pending',
    created_at        text NOT NULL,
    expires_at        text NOT NULL,
    media_ref         text
);
CREATE INDEX IF NOT EXISTS pending_enrollments_expires_idx ON pending_enrollments(expires_at);
-- Idempotente: alinea tablas ya creadas. `media_ref` (foto original) es imprescindible para el cierre
-- tipo imagen al resolver la desambiguación (ADR-0020); sin él, el cierre degradaba a texto.
ALTER TABLE pending_enrollments ADD COLUMN IF NOT EXISTS media_ref text;
"""


def _faces_to_json(faces: tuple[PendingFace, ...]) -> str:
    return json.dumps([
        {"index": f.index, "embedding": list(f.embedding),
         "bbox": ([f.bbox.x1, f.bbox.y1, f.bbox.x2, f.bbox.y2] if f.bbox else None),
         "det_score": f.det_score, "crop_ref": f.crop_ref}
        for f in faces
    ])


def _faces_from_json(raw) -> tuple[PendingFace, ...]:
    data = raw if isinstance(raw, list) else json.loads(raw)
    out = []
    for f in data:
        b = f.get("bbox")
        out.append(PendingFace(
            index=f["index"], embedding=tuple(f["embedding"]),
            bbox=(BBox(*b) if b else None), det_score=f.get("det_score", 0.0),
            crop_ref=f.get("crop_ref")))
    return tuple(out)


class PgPendingEnrollmentStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    def _ensure(self):
        if self._conn is None:
            import psycopg
            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def init_schema(self) -> None:
        self._ensure().execute(_DDL)

    def save(self, pending: PendingEnrollment) -> None:
        # DO UPDATE (no DO NOTHING): la transición a `awaiting_others` (ADR-0021) actualiza status/faces
        # sobre el mismo disambiguation_id; con DO NOTHING esos cambios se perdían. La reentrega del
        # report.ingested ya está deduplicada aguas arriba por event_id (ADR-0018).
        self._ensure().execute(
            """INSERT INTO pending_enrollments
                 (disambiguation_id, entity_id, report_id, conversation_key, faces, reporter,
                  status, created_at, expires_at, media_ref)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
               ON CONFLICT (disambiguation_id) DO UPDATE SET
                  status = EXCLUDED.status, faces = EXCLUDED.faces, media_ref = EXCLUDED.media_ref""",
            (pending.disambiguation_id, pending.entity_id, pending.report_id,
             pending.conversation_key, _faces_to_json(pending.faces),
             json.dumps(pending.reporter) if pending.reporter else None,
             pending.status, pending.created_at, pending.expires_at, pending.media_ref),
        )

    def get(self, disambiguation_id: str) -> Optional[PendingEnrollment]:
        cur = self._ensure().execute(
            """SELECT disambiguation_id, entity_id, report_id, conversation_key, faces, reporter,
                      status, created_at, expires_at, media_ref
               FROM pending_enrollments WHERE disambiguation_id = %s""",
            (disambiguation_id,))
        row = cur.fetchone()
        if row is None:
            return None
        reporter = row[5] if isinstance(row[5], (dict, type(None))) else json.loads(row[5])
        return PendingEnrollment(
            disambiguation_id=row[0], entity_id=row[1], report_id=row[2],
            conversation_key=row[3], faces=_faces_from_json(row[4]), reporter=reporter,
            status=row[6], created_at=row[7], expires_at=row[8], media_ref=row[9])

    def mark_resolved(self, disambiguation_id: str) -> None:
        self._ensure().execute(
            "UPDATE pending_enrollments SET status = 'resolved' WHERE disambiguation_id = %s",
            (disambiguation_id,))

    def purge_expired(self, now_iso: str) -> int:
        cur = self._ensure().execute(
            "DELETE FROM pending_enrollments WHERE expires_at < %s", (now_iso,))
        return cur.rowcount
