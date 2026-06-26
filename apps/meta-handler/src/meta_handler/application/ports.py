"""Puertos del Meta Handler. Los adaptadores (SQS, Vault/JWE, store) los implementan."""
from __future__ import annotations

from typing import Protocol


class InboundPublisher(Protocol):
    """Publica los eventos normalizados a sus colas (inbound.text / inbound.media)."""

    def publish_text(self, envelope: dict) -> None: ...
    def publish_media(self, envelope: dict) -> None: ...


class BodyCipher(Protocol):
    """Cifra el cuerpo con PII en JWE antes de ponerlo en el bus (ADR-0011/0012/0008)."""

    def encrypt(self, plaintext: str) -> str: ...


class EventLog(Protocol):
    """Traza por pasos (Event + EventAction) para auditoría (ADR-0005). No-op en MVP."""

    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None: ...
