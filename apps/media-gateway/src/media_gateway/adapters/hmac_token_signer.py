"""TokenSigner con HMAC-SHA256 en proceso (tests/dev). El real es `kms_token_signer` (clave en KMS).

La clave vive en memoria; en producción la KEK del HMAC está en KMS/Vault (ADR-0008). `verify` usa
comparación en tiempo constante.
"""
from __future__ import annotations

import base64
import hashlib
import hmac


class HmacTokenSigner:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def sign(self, token_id: str, exp: int) -> str:
        mac = hmac.new(self._key, f"{token_id}.{exp}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()

    def verify(self, token_id: str, exp: int, sig: str) -> bool:
        return hmac.compare_digest(self.sign(token_id, exp), sig)
