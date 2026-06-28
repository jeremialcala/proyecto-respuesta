"""Adaptador ArcFace/IResNet100 (InsightFace) — embeddings faciales de 512-d (ADR-0013).

Sustituye a OpenCV SFace como motor primario; corre sobre GPU RTX 3090 (ADR-0001/0006).
`insightface`/`onnxruntime-gpu` se importan de forma perezosa para no acoplar el import del
paquete a dependencias pesadas (los tests del dominio no las necesitan).

Implementación pendiente de afinado (fase 03/04):
- Cargar `FaceAnalysis(name=...)` con detector SCRFD + reconocedor ArcFace (det+rec).
- map_image: detectar todos los rostros, alinear por landmarks y extraer embedding 512-d normalizado.
- map_video: tracking + Hierarchical Windowing + agregación por track (ADR-0004).
"""
from __future__ import annotations

from ..config import ArcFaceParams, QualityThresholds
from ..domain.models import BBox, FaceMap, FaceQuality


class ArcFaceMapper:
    def __init__(self, model_root: str, params: ArcFaceParams | None = None,
                 quality: QualityThresholds | None = None) -> None:
        self._model_root = model_root
        self._p = params or ArcFaceParams()
        self._q = quality or QualityThresholds()
        self._app = None  # FaceAnalysis perezoso

    def _ensure_loaded(self):
        if self._app is None:
            from insightface.app import FaceAnalysis  # import perezoso
            providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                         if self._p.use_gpu else ["CPUExecutionProvider"])
            app = FaceAnalysis(name="buffalo_l", root=self._model_root, providers=providers)
            app.prepare(ctx_id=0 if self._p.use_gpu else -1)
            self._app = app
        return self._app

    def _to_facemap(self, face) -> FaceMap:
        import numpy as np  # import perezoso (la imagen/decodificación trae numpy)
        emb = np.asarray(face.normed_embedding, dtype="float32")  # 512-d ya normalizado
        x1, y1, x2, y2 = (int(v) for v in face.bbox.astype(int))
        size = int(min(x2 - x1, y2 - y1))
        quality = FaceQuality(size_px=size, blur_var=float("nan"), yaw=0.0, pitch=0.0)
        det = float(getattr(face, "det_score", 0.0) or 0.0)
        return FaceMap(embedding=tuple(emb.tolist()), quality=quality,
                       bbox=BBox(x1, y1, x2, y2), det_score=det)

    def map_image(self, image_bytes: bytes) -> list[FaceMap]:
        import cv2
        import numpy as np
        app = self._ensure_loaded()
        arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return []
        faces = app.get(arr)
        out = [self._to_facemap(f) for f in faces if int(min(*(f.bbox[2:] - f.bbox[:2]))) >= self._q.min_size_px]
        return out

    def crop_faces(self, image_bytes: bytes, bboxes: list[BBox]) -> list[bytes]:
        """Recorta cada rostro (JPEG) para la desambiguación (ADR-0016). Clampa a los bordes."""
        import cv2
        import numpy as np
        arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return []
        h, w = arr.shape[:2]
        crops: list[bytes] = []
        for b in bboxes:
            x1, y1 = max(0, b.x1), max(0, b.y1)
            x2, y2 = min(w, b.x2), min(h, b.y2)
            if x2 <= x1 or y2 <= y1:
                crops.append(b"")
                continue
            ok, buf = cv2.imencode(".jpg", arr[y1:y2, x1:x2])
            crops.append(buf.tobytes() if ok else b"")
        return crops

    def map_video(self, video_bytes: bytes) -> list[FaceMap]:
        # TODO(fase-03): muestreo de frames + tracking + Hierarchical Windowing (ADR-0004).
        raise NotImplementedError("map_video: tracking + windowing pendiente (fase 03)")
