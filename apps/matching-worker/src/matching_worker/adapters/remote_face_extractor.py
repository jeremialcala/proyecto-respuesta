"""Extractor facial REMOTO (ADR-0019): implementa `FaceMapper` delegando la extracción al plano de
inferencia por el bus, sin GPU in-region.

`map_image` envía la imagen mínima vía `RequestReplyClient` y reconstruye los `FaceMap` desde los
vectores que devuelve el nodo de inferencia (que descarta la imagen — minimización A04). `crop_faces`
es CPU/cv2 y **se mantiene in-region**: se delega en un `ArcFaceMapper` usado solo para recortar (su
`crop_faces` no carga el modelo, así que no requiere GPU ni descarga de pesos). `map_video` queda como
el local (pendiente, fase 03).

El destino del plano de inferencia (EKS sa-east-1, on-prem o vast.ai Secure Cloud) es **configuración**:
este adaptador no lo conoce, solo habla con el bus (ADR-0019 §2).
"""
from __future__ import annotations

from ..application.face_codec import face_from_dict
from ..application.ports import RequestReplyClient
from ..domain.models import BBox, FaceMap


class RemoteFaceExtractor:
    def __init__(self, client: RequestReplyClient, cropper, *, timeout: float = 30.0) -> None:
        self._client = client
        self._cropper = cropper      # ArcFaceMapper: solo para crop_faces (cv2, sin cargar modelo)
        self._timeout = timeout

    def map_image(self, image_bytes: bytes) -> list[FaceMap]:
        faces = self._client.request(image_bytes, timeout=self._timeout)
        return [face_from_dict(f) for f in faces]

    def crop_faces(self, image_bytes: bytes, bboxes: list[BBox]) -> list[bytes]:
        return self._cropper.crop_faces(image_bytes, bboxes)

    def map_video(self, video_bytes: bytes) -> list[FaceMap]:
        raise NotImplementedError("map_video remoto: pendiente (fase 03)")
