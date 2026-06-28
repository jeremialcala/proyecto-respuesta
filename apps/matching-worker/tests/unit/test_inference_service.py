"""InferenceService (ADR-0019): el plano de inferencia devuelve solo vectores, sin estado."""
import base64

from matching_worker.application.face_codec import face_from_dict, face_to_dict
from matching_worker.application.inference_service import InferenceService
from matching_worker.domain.models import BBox, FaceMap, FaceQuality


class FakeMapper:
    def __init__(self, faces, *, raise_on_empty=False):
        self._faces = faces
        self.calls = []

    def map_image(self, image_bytes):
        self.calls.append(image_bytes)
        return self._faces


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))


def _face(emb=(0.1, 0.2), size=120, det=0.9, x1=0):
    return FaceMap(embedding=emb, quality=FaceQuality(size_px=size, blur_var=80.0, yaw=0.0, pitch=0.0),
                   bbox=BBox(x1, 0, x1 + 90, 100), det_score=det)


def _request(job_id="job_1", image=b"img"):
    return {"event_id": "x1", "event_type": "face.extract.requested",
            "payload": {"job_id": job_id, "image_b64": base64.b64encode(image).decode("ascii")}}


def test_extract_publishes_face_embedded_with_vectors():
    mapper = FakeMapper([_face(emb=(0.3, 0.4), x1=0), _face(emb=(0.5, 0.6), x1=300)])
    bus = FakeBus()
    InferenceService(mapper, bus).on_extract_requested(_request("job_42"))
    assert len(bus.events) == 1
    event, payload = bus.events[0]
    assert event == "face.embedded"
    assert payload["job_id"] == "job_42"
    assert len(payload["faces"]) == 2
    assert payload["faces"][0]["embedding"] == [0.3, 0.4]   # solo el vector + geometría
    assert payload["faces"][1]["bbox"] == [300, 0, 390, 100]
    assert mapper.calls == [b"img"]                          # decodificó la imagen mínima


def test_unreadable_image_returns_empty_faces():
    mapper = FakeMapper([])
    bus = FakeBus()
    # base64 inválido → image vacía → faces []
    InferenceService(mapper, bus).on_extract_requested(
        {"event_id": "x", "payload": {"job_id": "j", "image_b64": "!!!notb64!!!"}})
    assert bus.events[0][1]["faces"] == []


def test_missing_fields_is_ignored():
    bus = FakeBus()
    InferenceService(FakeMapper([]), bus).on_extract_requested({"payload": {"job_id": "j"}})
    assert bus.events == []


def test_codec_round_trips_facemap():
    f = _face(emb=(0.7, 0.8, 0.9), size=88, det=0.77, x1=10)
    back = face_from_dict(face_to_dict(f))
    assert back.embedding == (0.7, 0.8, 0.9)
    assert back.bbox == BBox(10, 0, 100, 100)
    assert back.det_score == 0.77
    assert back.quality.size_px == 88
