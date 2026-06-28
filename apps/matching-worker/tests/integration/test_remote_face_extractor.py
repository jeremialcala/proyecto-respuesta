"""RemoteFaceExtractor + selección por config (ADR-0019): extracción remota, recorte local."""
from matching_worker.adapters.arcface_facemapper import ArcFaceMapper
from matching_worker.adapters.remote_face_extractor import RemoteFaceExtractor
from matching_worker.config import WorkerConfig
from matching_worker.domain.models import BBox


class FakeClient:
    """Devuelve faces (dicts del face_codec) sin tocar la red."""
    def __init__(self, faces):
        self._faces = faces
        self.requests = []

    def request(self, image_bytes, *, timeout):
        self.requests.append((image_bytes, timeout))
        return self._faces


class FakeCropper:
    def __init__(self):
        self.calls = []

    def crop_faces(self, image_bytes, bboxes):
        self.calls.append((image_bytes, bboxes))
        return [b"crop"] * len(bboxes)


def test_map_image_round_trips_to_facemaps():
    client = FakeClient([
        {"embedding": [0.1, 0.2], "bbox": [0, 0, 90, 100], "det_score": 0.9, "size_px": 90},
        {"embedding": [0.3, 0.4], "bbox": [300, 0, 390, 100], "det_score": 0.8, "size_px": 90},
    ])
    ext = RemoteFaceExtractor(client, cropper=FakeCropper(), timeout=12.0)
    faces = ext.map_image(b"the-image")
    assert [f.embedding for f in faces] == [(0.1, 0.2), (0.3, 0.4)]
    assert faces[1].bbox == BBox(300, 0, 390, 100)
    assert client.requests == [(b"the-image", 12.0)]      # envió la imagen con el timeout configurado


def test_crop_faces_runs_locally_without_touching_client():
    client = FakeClient([])
    cropper = FakeCropper()
    ext = RemoteFaceExtractor(client, cropper=cropper)
    out = ext.crop_faces(b"img", [BBox(0, 0, 10, 10), BBox(5, 5, 15, 15)])
    assert out == [b"crop", b"crop"]
    assert cropper.calls and not client.requests        # el recorte (cv2/CPU) no usa el cliente remoto


def test_config_selects_local_by_default():
    from matching_worker.__main__ import build_face_mapper
    mapper = build_face_mapper(WorkerConfig(face_extractor="local"))
    assert isinstance(mapper, ArcFaceMapper)


def test_config_selects_remote_extractor():
    from matching_worker.__main__ import build_face_mapper
    cfg = WorkerConfig(face_extractor="remote",
                       extract_topic_arn="arn:aws:sns:sa-east-1:0:face-extract-requested",
                       face_embedded_reply_queue_url="https://sqs/q/face-embedded-reply")
    mapper = build_face_mapper(cfg)
    assert isinstance(mapper, RemoteFaceExtractor)
