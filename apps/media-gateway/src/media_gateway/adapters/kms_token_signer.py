"""HMAC del token con clave en KMS (`GenerateMac`/`VerifyMac`, HMAC_SHA_256). ADR-0008/0017 §7.

La clave del HMAC nunca sale de KMS; rota por política de KMS. El mensaje firmado es `token_id.exp`,
igual que el firmante en proceso (`hmac_token_signer`), para que ambos sean intercambiables. `boto3`
perezoso.
"""
from __future__ import annotations

import base64


class KmsTokenSigner:
    def __init__(self, key_id: str, region: str) -> None:
        self._key_id = key_id
        self._region = region
        self._kms = None

    def _ensure(self):
        if self._kms is None:
            import boto3
            self._kms = boto3.client("kms", region_name=self._region)
        return self._kms

    def sign(self, token_id: str, exp: int) -> str:
        kms = self._ensure()
        mac = kms.generate_mac(KeyId=self._key_id, MacAlgorithm="HMAC_SHA_256",
                               Message=f"{token_id}.{exp}".encode())["Mac"]
        return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()

    def verify(self, token_id: str, exp: int, sig: str) -> bool:
        kms = self._ensure()
        try:
            pad = "=" * (-len(sig) % 4)
            mac = base64.urlsafe_b64decode(sig + pad)
        except (ValueError, TypeError):
            return False
        resp = kms.verify_mac(KeyId=self._key_id, MacAlgorithm="HMAC_SHA_256",
                              Message=f"{token_id}.{exp}".encode(), Mac=mac)
        return bool(resp.get("MacValid", False))
