"""Serialización de `FaceMap` para el contrato efímero del plano de inferencia (ADR-0019).

El plano de inferencia (GPU, posiblemente en burst on-demand) devuelve **solo el vector** y la geometría
mínima por rostro; la imagen nunca se persiste ni se devuelve. Estos helpers son la frontera entre el
dominio (`FaceMap`) y el JSON del bus, compartidos por el `InferenceService` (que publica) y el
`RemoteFaceExtractor` (que reconstruye). Puros: sin dependencias de infraestructura.
"""
from __future__ import annotations

from ..domain.models import BBox, FaceMap, FaceQuality


def face_to_dict(face: FaceMap) -> dict:
    b = face.bbox
    return {
        "embedding": list(face.embedding),
        "bbox": ([b.x1, b.y1, b.x2, b.y2] if b is not None else None),
        "det_score": face.det_score,
        "size_px": face.quality.size_px,
        "blur_var": face.quality.blur_var,
        "yaw": face.quality.yaw,
        "pitch": face.quality.pitch,
    }


def face_from_dict(d: dict) -> FaceMap:
    b = d.get("bbox")
    quality = FaceQuality(
        size_px=int(d.get("size_px", 0)),
        blur_var=float(d.get("blur_var", float("nan"))),
        yaw=float(d.get("yaw", 0.0)),
        pitch=float(d.get("pitch", 0.0)),
    )
    return FaceMap(
        embedding=tuple(d.get("embedding", ())),
        quality=quality,
        bbox=(BBox(*b) if b else None),
        det_score=float(d.get("det_score", 0.0)),
    )
