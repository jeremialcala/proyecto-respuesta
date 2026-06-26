"""Adaptador OpenCV YuNet + SFace (~128-d) — **FALLBACK** del motor primario ArcFace (ADR-0013).

Se conserva como ruta de degradación si la GPU on-prem (RTX 3090) no está disponible (ArcFace en CPU
es lento). Genera embeddings de ~128-d **incompatibles** con los 512-d de ArcFace → un cambio a este
fallback exige re-generar el índice y los embeddings con la misma versión de modelo (ADR-0007/0013).
"""
from __future__ import annotations

from ..domain.models import FaceMap


class OpenCVFaceMapper:
    def __init__(self, detector_model: str, recognizer_model: str) -> None:
        self._detector_model = detector_model
        self._recognizer_model = recognizer_model
        # TODO(fallback): inicializar cv2.FaceDetectorYN / cv2.FaceRecognizerSF

    def map_image(self, image_bytes: bytes) -> list[FaceMap]:
        raise NotImplementedError("Fallback YuNet+SFace (~128-d) — pendiente; primario es ArcFace")

    def map_video(self, video_bytes: bytes) -> list[FaceMap]:
        raise NotImplementedError("Fallback YuNet+SFace — tracking pendiente")
