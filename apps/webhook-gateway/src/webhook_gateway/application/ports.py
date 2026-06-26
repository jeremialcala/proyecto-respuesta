"""Puertos de la capa de aplicación. Los adaptadores (Redis, SQS) los implementan."""
from __future__ import annotations

from typing import Protocol


class IdempotencyStore(Protocol):
    """Guarda de idempotencia por message_id (Meta reintrega). Redis con TTL."""

    def seen(self, key: str) -> bool:
        """Marca `key` y devuelve True si **ya existía** (entrega duplicada)."""
        ...


class RawPublisher(Protocol):
    """Publica el payload crudo (envuelto en el sobre estándar) en la cola `meta.received`."""

    def publish_raw(self, envelope: dict) -> None: ...
