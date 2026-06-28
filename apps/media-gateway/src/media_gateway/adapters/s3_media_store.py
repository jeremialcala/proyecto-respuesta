"""Lectura de la bóveda S3 por `media_ref` (`s3://bucket/key`). `boto3` perezoso (ADR-0008/0017).

Contraparte de lectura del `S3MediaStore` del vault-worker (que escribe). Devuelve el ciphertext y la
metadata necesaria para descifrar (`wrapped_dek`, `key_id`, `subject`) y para validar/servir (`scan`,
`content_type`). No descifra: eso es responsabilidad del `EnvelopeCipher`.
"""
from __future__ import annotations

import base64


class S3MediaStore:
    def __init__(self, region: str) -> None:
        self._region = region
        self._s3 = None

    def _ensure(self):
        if self._s3 is None:
            import boto3
            self._s3 = boto3.client("s3", region_name=self._region)
        return self._s3

    @staticmethod
    def _split(media_ref: str) -> tuple[str, str]:
        if not media_ref.startswith("s3://"):
            raise KeyError(media_ref)
        bucket, _, key = media_ref[len("s3://"):].partition("/")
        if not bucket or not key:
            raise KeyError(media_ref)
        return bucket, key

    def get(self, media_ref: str) -> tuple[bytes, dict]:
        bucket, key = self._split(media_ref)
        s3 = self._ensure()
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
        except s3.exceptions.NoSuchKey as exc:  # objeto ausente → KeyError (404 fail-closed)
            raise KeyError(media_ref) from exc
        ciphertext = resp["Body"].read()
        md = dict(resp.get("Metadata", {}))  # S3 user metadata (claves en minúscula)
        if "wrapped_dek" in md:
            md["wrapped_dek"] = base64.b64decode(md["wrapped_dek"])
        return ciphertext, md
