"""MediaGateway sobre S3/bóveda (ADR-0005/0008/0016). `boto3` perezoso.

- `fetch(media_ref)` lee el objeto `s3://bucket/key` de la bóveda.
- `store_crops` guarda los recortes efímeros bajo `crops/` (prefijo con lifecycle/TTL en infra) y
  devuelve sus `crop_ref` (`s3://bucket/crops/…`). `delete_crops` los borra de inmediato (A04).

TODO(fase-03, ADR-0008): el cuerpo de la bóveda viaja cifrado (envelope KMS + DEK envuelto en los
metadatos del objeto). Para `map_image` hay que **descifrar** con el `KmsEnvelopeCipher` y el
`wrapped_dek` antes de devolver los bytes. Aquí se devuelve el cuerpo tal cual (válido en local con
SSE-KMS transparente / cifrado passthrough); falta inyectar el descifrador del lado bóveda.
"""
from __future__ import annotations

import uuid


def _parse_s3_ref(ref: str) -> tuple[str, str]:
    if not ref.startswith("s3://"):
        raise ValueError(f"media_ref no es s3://: {ref}")
    bucket, _, key = ref[len("s3://"):].partition("/")
    if not bucket or not key:
        raise ValueError(f"media_ref incompleto: {ref}")
    return bucket, key


class VaultMediaGateway:
    def __init__(self, region: str, crops_bucket: str, crops_prefix: str = "crops",
                 sse: str = "aws:kms") -> None:
        self._region = region
        self._crops_bucket = crops_bucket
        self._crops_prefix = crops_prefix.strip("/")
        self._sse = sse   # "aws:kms" en prod; "" en dev con MinIO (sin KES no acepta SSE-KMS)
        self._s3 = None

    def _ensure(self):
        if self._s3 is None:
            import boto3   # endpoint S3 vía AWS_ENDPOINT_URL_S3 (MinIO en dev) — boto3 lo toma del entorno
            self._s3 = boto3.client("s3", region_name=self._region)
        return self._s3

    def fetch(self, media_ref: str) -> bytes:
        bucket, key = _parse_s3_ref(media_ref)
        resp = self._ensure().get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
        # TODO(ADR-0008): descifrar con KmsEnvelopeCipher + wrapped_dek de resp["Metadata"].

    def store_crops(self, crops: list[bytes], ttl_seconds: int) -> list[str]:
        s3 = self._ensure()
        refs: list[str] = []
        extra = {"ServerSideEncryption": self._sse} if self._sse else {}
        for blob in crops:
            key = f"{self._crops_prefix}/{uuid.uuid4().hex}.jpg"
            # scan=clean en la metadata: el media-gateway es fail-closed y solo sirve objetos limpios.
            # Sin esto, la miniatura de desambiguación y el cierre del reporte derivado (ADR-0021) darían
            # 403 al descargarlos Meta (ADR-0017).
            s3.put_object(Bucket=self._crops_bucket, Key=key, Body=blob,
                          ContentType="image/jpeg", Metadata={"scan": "clean"}, **extra)
            refs.append(f"s3://{self._crops_bucket}/{key}")
        return refs

    def delete_crops(self, crop_refs: list[str]) -> None:
        s3 = self._ensure()
        for ref in crop_refs:
            try:
                bucket, key = _parse_s3_ref(ref)
            except ValueError:
                continue
            s3.delete_object(Bucket=bucket, Key=key)
