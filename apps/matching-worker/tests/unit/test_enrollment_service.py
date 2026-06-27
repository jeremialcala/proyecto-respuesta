"""EnrollmentService (ADR-0016): ramas de enrolamiento y desambiguación multi-rostro con fakes."""
from datetime import datetime, timedelta, timezone

import pytest

from matching_worker.application.enrollment_service import EnrollmentService
from matching_worker.config import QualityThresholds
from matching_worker.domain.models import BBox, FaceMap, FaceQuality


# --- fakes en memoria (sin GPU ni infraestructura) ---
class FakeMapper:
    def __init__(self, faces):
        self._faces = faces
        self.cropped = None

    def map_image(self, image_bytes):
        return self._faces

    def crop_faces(self, image_bytes, bboxes):
        self.cropped = bboxes
        return [f"crop{i}".encode() for i in range(len(bboxes))]


class FakeMedia:
    def __init__(self):
        self.deleted = []
        self.stored = []

    def fetch(self, media_ref):
        return b"img"

    def store_crops(self, crops, ttl_seconds):
        refs = [f"vault://crop/{i}" for i in range(len(crops))]
        self.stored.append((refs, ttl_seconds))
        return refs

    def delete_crops(self, crop_refs):
        self.deleted.extend(crop_refs)


class FakeStore:
    def __init__(self):
        self.refs = []

    def add_reference(self, entity_id, embedding):
        self.refs.append((entity_id, tuple(embedding)))

    def delete_entity(self, entity_id):
        self.refs = [r for r in self.refs if r[0] != entity_id]

    def all_references(self):
        return list(self.refs)


class FakeIndex:
    def __init__(self):
        self.rebuilds = 0

    def rebuild_from(self, store):
        self.rebuilds += 1

    def search(self, embedding, k):
        return []


class FakePending:
    def __init__(self):
        self.items = {}
        self.resolved = []

    def save(self, pending):
        self.items[pending.disambiguation_id] = pending

    def get(self, disambiguation_id):
        return self.items.get(disambiguation_id)

    def mark_resolved(self, disambiguation_id):
        self.resolved.append(disambiguation_id)
        cur = self.items.get(disambiguation_id)
        if cur is not None:
            self.items[disambiguation_id] = _replace_status(cur, "resolved")

    def purge_expired(self, now_iso):
        gone = [k for k, v in self.items.items() if v.expires_at < now_iso]
        for k in gone:
            del self.items[k]
        return len(gone)


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))

    def types(self):
        return [e for e, _ in self.events]

    def payload(self, event):
        return next(p for e, p in self.events if e == event)


def _replace_status(pending, status):
    from dataclasses import replace
    return replace(pending, status=status)


def _face(emb=(0.1, 0.2), size=120, blur=80.0, x1=0, det=0.9):
    return FaceMap(embedding=emb, quality=FaceQuality(size_px=size, blur_var=blur, yaw=0.0, pitch=0.0),
                   bbox=BBox(x1, 0, x1 + 90, 100), det_score=det)


def _svc(faces, *, pending=None, fixed_id="dis_fixed", now=None):
    fm, media, store, index, pend, bus = (
        FakeMapper(faces), FakeMedia(), FakeStore(), FakeIndex(), pending or FakePending(), FakeBus())
    now_fn = (lambda: now) if now else (lambda: datetime.now(timezone.utc))
    svc = EnrollmentService(fm, media, store, index, pend, bus, QualityThresholds(),
                            pending_ttl_seconds=3600, now_fn=now_fn, id_fn=lambda: fixed_id)
    return svc, dict(fm=fm, media=media, store=store, index=index, pending=pend, bus=bus)


def _ingested(entity="ent_1", report="rep_1", media_ref="vault://m/1", ck="conv_1"):
    return {"event_id": "e1", "event_type": "report.ingested",
            "payload": {"entity_id": entity, "report_id": report, "media_ref": media_ref,
                        "conversation_key": ck, "bot_id": "bot-1", "channel": "whatsapp",
                        "contact_ref": "wa:rep"}}


# --- report.ingested ---
def test_zero_faces_fails_no_face():
    svc, d = _svc([])
    svc.on_report_ingested(_ingested())
    assert d["bus"].types() == ["enrollment.failed"]
    assert d["bus"].payload("enrollment.failed")["reason"] == "no_face"
    assert d["store"].refs == []


def test_single_face_enrolls_and_refreshes_index():
    svc, d = _svc([_face(emb=(0.3, 0.4))])
    svc.on_report_ingested(_ingested())
    assert d["store"].refs == [("ent_1", (0.3, 0.4))]
    assert d["index"].rebuilds == 1
    enrolled = d["bus"].payload("entity.enrolled")
    assert enrolled["entity_id"] == "ent_1" and enrolled["source"] == "report.ingested"
    # la identidad del reportante viaja para el feedback "reporte completo" (ADR-0016)
    assert enrolled["contact_ref"] == "wa:rep" and enrolled["bot_id"] == "bot-1"


def test_tiny_background_faces_are_filtered_before_counting():
    # 1 rostro válido + 1 diminuto → cuenta como 1 → enrola (no pregunta).
    svc, d = _svc([_face(emb=(0.5, 0.6)), _face(size=40)])
    svc.on_report_ingested(_ingested())
    assert "entity.enrolled" in d["bus"].types()
    assert "face.disambiguation.requested" not in d["bus"].types()


def test_multi_face_requests_disambiguation_and_does_not_enroll():
    svc, d = _svc([_face(x1=0), _face(x1=300)])
    svc.on_report_ingested(_ingested())
    assert d["store"].refs == []                       # NO enrola
    assert d["index"].rebuilds == 0
    req = d["bus"].payload("face.disambiguation.requested")
    assert req["disambiguation_id"] == "dis_fixed"
    assert len(req["faces"]) == 2
    assert req["faces"][0]["crop_ref"] == "vault://crop/0"
    assert req["faces"][1]["bbox"] == [300, 0, 390, 100]
    assert d["pending"].get("dis_fixed") is not None   # pendiente persistido


# --- face.disambiguation.resolved ---
def _resolve(dis="dis_fixed", **payload):
    return {"event_id": "r1", "event_type": "face.disambiguation.resolved",
            "payload": {"disambiguation_id": dis, **payload}}


def test_resolved_enrolls_selected_and_purges_all_crops():
    pend = FakePending()
    svc, d = _svc([_face(emb=(1.0, 0.0), x1=0), _face(emb=(0.0, 1.0), x1=300)], pending=pend)
    svc.on_report_ingested(_ingested())
    svc.on_disambiguation_resolved(_resolve(selected_index=1))
    assert d["store"].refs == [("ent_1", (0.0, 1.0))]     # solo el elegido
    assert set(d["media"].deleted) == {"vault://crop/0", "vault://crop/1"}  # purga todos
    assert "dis_fixed" in d["pending"].resolved
    assert "entity.enrolled" in d["bus"].types()


def test_none_of_these_fails_and_purges():
    svc, d = _svc([_face(x1=0), _face(x1=300)])
    svc.on_report_ingested(_ingested())
    svc.on_disambiguation_resolved(_resolve(action="none_of_these"))
    assert d["store"].refs == []
    assert set(d["media"].deleted) == {"vault://crop/0", "vault://crop/1"}
    assert d["bus"].payload("enrollment.failed")["reason"] == "no_subject_in_photo"


def test_out_of_range_selection_fails_without_enrolling():
    svc, d = _svc([_face(x1=0), _face(x1=300)])
    svc.on_report_ingested(_ingested())
    svc.on_disambiguation_resolved(_resolve(selected_index=5))
    assert d["store"].refs == []
    assert d["bus"].payload("enrollment.failed")["reason"] == "invalid_selection"


def test_resolved_for_unknown_id_reports_expired():
    svc, d = _svc([])
    svc.on_disambiguation_resolved(_resolve(dis="nope", selected_index=0))
    assert d["bus"].payload("enrollment.failed")["reason"] == "expired"


def test_duplicate_resolved_is_noop_idempotent():
    svc, d = _svc([_face(emb=(1.0, 0.0), x1=0), _face(emb=(0.0, 1.0), x1=300)])
    svc.on_report_ingested(_ingested())
    svc.on_disambiguation_resolved(_resolve(selected_index=0))
    refs_after_first = list(d["store"].refs)
    svc.on_disambiguation_resolved(_resolve(selected_index=0))   # duplicado
    assert d["store"].refs == refs_after_first                   # no enrola de nuevo


def test_expired_pending_on_resolve_reports_expired_and_purges():
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    pend = FakePending()
    # crea el pendiente con un "now" en el pasado para que ya esté vencido al resolver.
    svc_old, d_old = _svc([_face(x1=0), _face(x1=300)], pending=pend, now=past)
    svc_old.on_report_ingested(_ingested())
    # ahora resolvemos con el reloj real (muy posterior al expires_at)
    svc_new, _ = _svc([], pending=pend)
    # reusar el mismo bus/media para observar efectos
    svc_new._media = d_old["media"]; svc_new._bus = d_old["bus"]
    svc_new.on_disambiguation_resolved(_resolve(selected_index=0))
    assert d_old["bus"].payload("enrollment.failed")["reason"] == "expired"
    assert set(d_old["media"].deleted) == {"vault://crop/0", "vault://crop/1"}


def test_missing_entity_or_media_is_ignored():
    svc, d = _svc([_face()])
    svc.on_report_ingested({"payload": {"report_id": "r"}})   # sin entity_id/media_ref
    assert d["bus"].events == []
