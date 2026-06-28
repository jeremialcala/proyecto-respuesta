"""Cipher passthrough (SOLO dev/local): guarda el binario en claro, sin envolver DEK (ADR-0008).

En local el matching-worker lee los bytes de la bóveda **sin descifrar** (ver
`matching_worker.adapters.vault_media_gateway.fetch`, que es un TODO de descifrado). Para que el
camino de la foto funcione end-to-end con S3 persistente (MinIO) sin depender de un KMS efímero, en
dev se guarda el JPEG plano. **Producción usa `KmsEnvelopeCipher`** (envelope real, ADR-0008); esto se
elige por config (`VAULT_CIPHER`).
"""
from __future__ import annotations

from ..domain.models import EncryptedObject


class PassthroughCipher:
    def encrypt(self, data: bytes, subject: str) -> EncryptedObject:
        # ciphertext == plano; no hay DEK envuelta. key_id marca que es dev (no descifrable como KMS).
        return EncryptedObject(ciphertext=data, wrapped_dek=b"", key_id="dev-plaintext", subject=subject)
