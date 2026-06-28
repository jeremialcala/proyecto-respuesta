"""Persistencia del objeto cifrado en S3 (bóveda / cuarentena). `boto3` perezoso (ADR-0008/0012)."""
from __future__ import annotations

import base64

from ..domain.models import EncryptedObject


class S3MediaStore:
    def __init__(self, media_bucket: str, quarantine_bucket: str, region: str,
                 sse: str = "aws:kms") -> None:
        self._media = media_bucket
        self._quar = quarantine_bucket
        self._region = region
        self._sse = sse   # "aws:kms" en prod; "" en dev con MinIO (sin KES no acepta SSE-KMS)
        self._s3 = None

    def _ensure(self):
        if self._s3 is None:
            import boto3   # endpoint S3 vía AWS_ENDPOINT_URL_S3 (MinIO en dev) — boto3 lo toma del entorno
            self._s3 = boto3.client("s3", region_name=self._region)
        return self._s3

    def put(self, obj: EncryptedObject, *, key: str, metadata: dict, quarantine: bool = False) -> str:
        bucket = self._quar if quarantine else self._media
        s3 = self._ensure()
        md = {k: str(v) for k, v in metadata.items()}
        md["wrapped_dek"] = base64.b64encode(obj.wrapped_dek).decode()
        md["key_id"] = obj.key_id
        md["subject"] = obj.subject
        extra = {"ServerSideEncryption": self._sse} if self._sse else {}
        s3.put_object(Bucket=bucket, Key=key, Body=obj.ciphertext, Metadata=md, **extra)
        return f"s3://{bucket}/{key}"
