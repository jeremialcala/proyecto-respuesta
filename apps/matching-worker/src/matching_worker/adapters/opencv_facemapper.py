"""Adaptador OpenCV: YuNet (detección) + SFace (embeddings). Esqueleto.

Implementación pendiente (fase 03):
- Cargar `face_detection_yunet_*.onnx` con `cv2.FaceDetectorYN_create`.
- Cargar `face_recognition_sface_*.onnx` con `cv2.FaceRecognizerSF_create`.
- map_image: detectar todos los rostros, alinear y extraer un embedding por rostro.
- map_video: tracking + Hierarchical Windowing + agregación por track (ADR-0004).
"""
from __future__ import annotations

from ..domain.models import FaceMap


class OpenCVFaceMapper:
    def __init__(self, detector_model: str, recognizer_model: str) -> None:
        self._detector_model = detector_model
        self._recognizer_model = recognizer_model
        # TODO(fase-03): inicializar cv2.FaceDetectorYN / cv2.FaceRecognizerSF

    def map_image(self, image_bytes: bytes) -> list[FaceMap]:
        raise NotImplementedError("TODO(fase-03): YuNet+SFace sobre imagen")

    def map_video(self, video_bytes: bytes) -> list[FaceMap]:
        raise NotImplementedError("TODO(fase-03): tracking + Hierarchical Windowing")
