"""Configuración del Worker de Bóveda (12-factor). ADR-0005 (bóveda) / 0008 (cifrado) / 0012 (SQS)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VaultConfig:
    aws_region: str = "sa-east-1"                  # ADR-0006
    input_queue_url: str = ""                       # SQS: inbound.media (lo publica el Meta Handler)
    stored_queue_url: str = ""                       # SQS/SNS: media.stored → motor de matching
    media_bucket: str = ""                           # S3: bóveda de medios cifrados (ADR-0008)
    quarantine_bucket: str = ""                       # S3: cuarentena de medios con malware
    kms_key_id: str = ""                             # KMS/Vault: KEK que envuelve la DEK por usuario
    graph_api_base: str = "https://graph.facebook.com/v20.0"
    cipher_mode: str = "kms"                          # kms (prod, ADR-0008) | passthrough (dev: JPEG plano)
    s3_sse: str = "aws:kms"                           # "" en dev con MinIO (sin KES no acepta SSE-KMS)
    max_messages: int = 10
    wait_time_seconds: int = 20
    producer: str = "vault-worker"

    @staticmethod
    def from_env() -> "VaultConfig":
        return VaultConfig(
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            input_queue_url=os.getenv("SQS_INPUT_QUEUE_URL", ""),
            stored_queue_url=os.getenv("SQS_STORED_QUEUE_URL", ""),
            media_bucket=os.getenv("MEDIA_BUCKET", ""),
            quarantine_bucket=os.getenv("QUARANTINE_BUCKET", ""),
            kms_key_id=os.getenv("KMS_KEY_ID", ""),
            graph_api_base=os.getenv("GRAPH_API_BASE", "https://graph.facebook.com/v20.0"),
            cipher_mode=os.getenv("VAULT_CIPHER", "kms"),
            s3_sse=os.getenv("S3_SSE", "aws:kms"),
            max_messages=int(os.getenv("SQS_MAX_MESSAGES", "10")),
            wait_time_seconds=int(os.getenv("SQS_WAIT_SECONDS", "20")),
        )
