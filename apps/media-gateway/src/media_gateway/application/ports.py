"""Puertos de la capa de aplicación (hexagonal). ADR-0017 (design §5).

Los adaptadores (Postgres, KMS, S3, Redis, auditoría encadenada) los implementan; el dominio y los
servicios solo dependen de estos `Protocol`. `MediaStore`/`EnvelopeCipher` reusan el contrato de
lectura de la bóveda del `vault-worker` (ADR-0005/0008).
"""
from __future__ import annotations

from typing import Protocol

from ..domain.models import Grant


class MediaStore(Protocol):
    """Lectura de la bóveda. Reusa el contrato del vault-worker (modo lectura)."""

    def get(self, media_ref: str) -> tuple[bytes, dict]:
        """Devuelve (ciphertext, metadata). `metadata` incluye `scan`, `content_type`, `subject`,
        `wrapped_dek`, `key_id` (ADR-0008). Lanza KeyError si el objeto no existe."""
        ...


class EnvelopeCipher(Protocol):
    """Descifrado de sobre: desenvuelve la DEK (encryption context del sujeto) y descifra (ADR-0008)."""

    def decrypt(self, ciphertext: bytes, metadata: dict) -> bytes: ...


class GrantStore(Protocol):
    """Ledger de concesiones en Postgres — autoridad de `used_count`/`revoked_at`/`expires_at`."""

    def create(self, grant: Grant) -> None: ...

    def get(self, token_id: str) -> Grant | None: ...

    def consume(self, token_id: str) -> bool:
        """Incrementa `used_count` de forma atómica. Devuelve False si está agotado, expirado o
        revocado (no debe servirse). True si la descarga puede proceder."""
        ...

    def revoke(self, token_id: str) -> None: ...

    def revoke_by_ref(self, *, media_ref: str | None = None, report_id: str | None = None,
                      entity_id: str | None = None) -> int:
        """Revoca en lote por referencia. Devuelve el número de concesiones revocadas."""
        ...

    def purge_expired(self, now_iso: str) -> int: ...


class TokenSigner(Protocol):
    """HMAC del token con clave en KMS/Vault (ADR-0008). Rechazo barato de manipulación."""

    def sign(self, token_id: str, exp: int) -> str: ...

    def verify(self, token_id: str, exp: int, sig: str) -> bool: ...


class FetcherAllowlist(Protocol):
    """¿Esta IP/User-Agent puede descargar para esta `audience`? (rangos de Meta, sesión, etc.)."""

    def is_allowed(self, audience: str, src_ip: str, user_agent: str) -> bool: ...


class RateLimiter(Protocol):
    """Límite por token/IP/global (Redis). `hit` devuelve True si se permite, False si se excede."""

    def hit(self, key: str) -> bool: ...


class AuditLog(Protocol):
    """Auditoría encadenada SHA-256 (ADR-0007): `grant.issued`, `grant.revoked`, `media.served`."""

    def record(self, event: str, data: dict) -> None: ...
