"""EnvelopeCipher fake (tests). El real es `kms_envelope_cipher` (unwrap DEK + AES-GCM, ADR-0008).

Devuelve el ciphertext tal cual: el fake del MediaStore ya guarda "plaintext" en el campo ciphertext.
"""
from __future__ import annotations


class PassthroughCipher:
    def decrypt(self, ciphertext: bytes, metadata: dict) -> bytes:
        return ciphertext
