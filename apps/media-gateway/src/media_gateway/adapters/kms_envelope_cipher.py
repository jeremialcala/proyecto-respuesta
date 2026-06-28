"""Descifrado de sobre: unwrap de la DEK vía KMS (encryption context del sujeto) + AES-GCM. ADR-0008.

Contraparte de descifrado del `KmsEnvelopeCipher` del vault-worker (que cifra). El plano del binario
nunca se persiste; se devuelve en memoria para transmitirlo. `boto3`/`cryptography` perezosos.

Formato (igual al de cifrado del vault-worker): `ciphertext = nonce(12) || AESGCM_ct`, AAD = subject.
"""
from __future__ import annotations


class KmsEnvelopeCipher:
    def __init__(self, region: str) -> None:
        self._region = region
        self._kms = None

    def _ensure(self):
        if self._kms is None:
            import boto3
            self._kms = boto3.client("kms", region_name=self._region)
        return self._kms

    def decrypt(self, ciphertext: bytes, metadata: dict) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # import perezoso
        subject = metadata["subject"]
        wrapped_dek = metadata["wrapped_dek"]
        kms = self._ensure()
        # Unwrap de la DEK; el encryption context ata la clave al sujeto (clave por usuario, ADR-0008).
        dek = kms.decrypt(CiphertextBlob=wrapped_dek,
                          EncryptionContext={"subject": subject})["Plaintext"]
        nonce, ct = ciphertext[:12], ciphertext[12:]
        return AESGCM(dek).decrypt(nonce, ct, subject.encode())
