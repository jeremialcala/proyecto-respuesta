"""Cifrado del cuerpo en JWE (ADR-0011/0012/0008).

MVP: implementación **placeholder** que delega a Vault Transit / clave por evento en fase 03. Por
ahora marca el cuerpo como no cifrado para no dar falsa sensación de seguridad. NO usar en producción
sin la integración real de Vault.
"""
from __future__ import annotations


class PassthroughCipher:
    """Placeholder explícito: NO cifra. Se reemplaza por el cifrador JWE/Vault en fase 03."""

    def encrypt(self, plaintext: str) -> str:
        return "PLAINTEXT(JWE-PENDIENTE):" + plaintext
