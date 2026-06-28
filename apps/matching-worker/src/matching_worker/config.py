"""Parámetros del motor (ADR-0004, enmendado por ADR-0013).

Motor de embedding: **ArcFace / IResNet100 (512-d)** sobre GPU on-prem RTX 3090 (ADR-0001/0006/0013).
Los umbrales son valores iniciales para ArcFace y se **recalibran** con datos reales (fase 04).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Dimensión del embedding ArcFace/IResNet100 (ADR-0013). SFace (128-d) queda como fallback.
EMBEDDING_DIM: int = 512


@dataclass(frozen=True)
class DriftParams:
    """Tolerancia a drift de edad sobre la distancia coseno (0=idéntico .. 1=distinto).

    `tau0` es el umbral base para **ArcFace** (a recalibrar en fase 04; ArcFace suele operar con
    umbrales de coseno distintos a SFace).
    """
    tau0: float = 0.60        # umbral base ArcFace/IResNet100 (recalibrar — fase 04)
    alpha: float = 0.015      # margen por año de age_gap
    beta: float = 0.10        # bump adicional si es menor
    delta_max: float = 0.15   # tope del margen de drift


@dataclass(frozen=True)
class FusionWeights:
    """Pesos base de la fusión multi-señal (dinámicos: se anulan si falta la señal).

    En el MVP el scoring es **solo-rostro** (ADR-0013): el wiring no suministra geo/text, por lo que
    el peso efectivo de ambos es 0. Estos pesos quedan como diseño para activar la fusión post-MVP.
    """
    face: float = 0.60
    geo: float = 0.25
    text: float = 0.15


@dataclass(frozen=True)
class QualityThresholds:
    min_size_px: int = 80      # lado mínimo del rostro
    min_blur_var: float = 40.0 # varianza del Laplaciano (más bajo = más borroso)
    max_abs_yaw: float = 45.0
    max_abs_pitch: float = 45.0


@dataclass(frozen=True)
class TrackingParams:
    """Agrupación de detecciones por track en video. Umbral MÁS estricto que el match (ADR-0004)."""
    reid_distance: float = 0.45   # debe ser < DriftParams.tau0
    min_iou: float = 0.30
    min_track_frames: int = 5


@dataclass(frozen=True)
class FaissParams:
    m: int = 32                # conexiones por nodo (biometría)
    ef_construction: int = 128
    ef_search: int = 32


@dataclass(frozen=True)
class ArcFaceParams:
    """Modelo facial (ADR-0013). InsightFace ArcFace + detector con landmarks."""
    model_name: str = "arcface"
    backbone: str = "iresnet100"
    detector: str = "scrfd"        # detección+landmarks (alternativa: retinaface)
    embedding_dim: int = EMBEDDING_DIM
    use_gpu: bool = True           # RTX 3090 (ADR-0001/0006)


@dataclass(frozen=True)
class WorkerConfig:
    """Configuración de runtime leída del entorno (12-factor). AWS SQS/SNS — ADR-0012/0016."""
    aws_region: str = "sa-east-1"                  # ADR-0006
    input_queue_url: str = ""                      # SQS: report.ingested (→ enrolamiento, ADR-0016)
    output_topic_arn: str = ""                     # SNS: candidate.generated (fan-out)
    pgvector_dsn: str = ""                          # fuente de verdad (ADR-0007)
    arcface_model_root: str = "/models/insightface"
    top_k: int = 10
    max_messages: int = 10                         # SQS batch
    wait_time_seconds: int = 20                     # long polling
    producer: str = "matching-worker"
    # --- enrolamiento y desambiguación (ADR-0016) ---
    disambiguation_resolved_queue_url: str = ""    # SQS: face.disambiguation.resolved
    entity_enrolled_topic_arn: str = ""            # SNS: entity.enrolled
    enrollment_failed_topic_arn: str = ""          # SNS: enrollment.failed
    disambiguation_requested_topic_arn: str = ""   # SNS: face.disambiguation.requested
    media_bucket: str = "respuesta-media"          # bóveda S3 (ADR-0005/0008)
    crops_bucket: str = ""                          # recortes efímeros; por defecto = media_bucket
    s3_sse: str = "aws:kms"                          # "" en dev con MinIO (sin KES no acepta SSE-KMS)
    pending_ttl_seconds: int = 86400               # TTL del PendingEnrollment (alinear ADR-0007/0015)
    purge_interval_seconds: int = 3600             # cada cuánto corre purge_expired
    media_gateway_url: str = ""                    # plano interno del media-gateway (revoke-by-ref, ADR-0017)

    @staticmethod
    def from_env() -> "WorkerConfig":
        media_bucket = os.getenv("MEDIA_BUCKET", "respuesta-media")
        return WorkerConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            input_queue_url=os.getenv("SQS_INPUT_QUEUE_URL", ""),
            output_topic_arn=os.getenv("SNS_OUTPUT_TOPIC_ARN", ""),
            pgvector_dsn=os.getenv("PGVECTOR_DSN", ""),
            arcface_model_root=os.getenv("ARCFACE_MODEL_ROOT", "/models/insightface"),
            top_k=int(os.getenv("MATCH_TOP_K", "10")),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
            disambiguation_resolved_queue_url=os.getenv("SQS_DISAMBIGUATION_RESOLVED_URL", ""),
            entity_enrolled_topic_arn=os.getenv("SNS_ENTITY_ENROLLED_ARN", ""),
            enrollment_failed_topic_arn=os.getenv("SNS_ENROLLMENT_FAILED_ARN", ""),
            disambiguation_requested_topic_arn=os.getenv("SNS_FACE_DISAMBIGUATION_REQUESTED_ARN", ""),
            media_bucket=media_bucket,
            crops_bucket=os.getenv("CROPS_BUCKET", media_bucket),
            s3_sse=os.getenv("S3_SSE", "aws:kms"),
            pending_ttl_seconds=int(os.getenv("PENDING_TTL_SECONDS", "86400")),
            purge_interval_seconds=int(os.getenv("PURGE_INTERVAL_SECONDS", "3600")),
            media_gateway_url=os.getenv("MEDIA_GATEWAY_URL", ""),
        )
