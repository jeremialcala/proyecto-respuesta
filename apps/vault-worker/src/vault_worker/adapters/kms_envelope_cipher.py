"""Cifrado de sobre con KMS/Vault: DEK por objeto envuelta por KEK (ADR-0008). `boto3` perezoso.

MVP: usa KMS GenerateDataKey para la DEK y cifra el binario con AES-GCM. La KEK/Política por usuario
(clave por sujeto) se afina en fase 03 con Vault Transit. El plano del binario nunca se persiste.
"""
from __future__ import annotations

import os

from ..domain.models import EncryptedObject


class KmsEnvelopeCipher:
    def __init__(self, key_id: str, region: str) -> None:
        self._key_id = key_id
        self._region = region
        self._kms = None

    def _ensure(self):
        if self._kms is None:
            import boto3
            self._kms = boto3.client("kms", region_name=self._region)
        return self._kms

    def encrypt(self, data: bytes, subject: str) -> EncryptedObject:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # import perezoso
        kms = self._ensure()
        # DEK de 256 bits; encryption context ata la clave al sujeto (clave por usuario, ADR-0008).
        dk = kms.generate_data_key(KeyId=self._key_id, KeySpec="AES_256",
                                   EncryptionContext={"subject": subject})
        nonce = os.urandom(12)
        ct = AESGCM(dk["Plaintext"]).encrypt(nonce, data, subject.encode())
        return EncryptedObject(ciphertext=nonce + ct, wrapped_dek=dk["CiphertextBlob"],
                               key_id=self._key_id, subject=subject)
