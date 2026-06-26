"""Descifrado del cuerpo (reverso del chatbot). MVP placeholder; real = Vault JWE (ADR-0008)."""
from __future__ import annotations

_PREFIX = "PLAINTEXT(JWE-PENDIENTE):"


class PassthroughCipher:
    def decrypt(self, jwe_body: str) -> str:
        return jwe_body[len(_PREFIX):] if jwe_body.startswith(_PREFIX) else jwe_body
