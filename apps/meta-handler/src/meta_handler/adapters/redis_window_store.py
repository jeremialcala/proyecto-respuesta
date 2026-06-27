"""Abre la ventana de servicio de 24h por contacto en Redis. `redis` perezoso.

Al recibir un mensaje del usuario, el Meta Handler marca `wa:window:{contact_ref}` con TTL 24h.
El `output-service` consulta esa misma clave para decidir texto libre vs plantilla HSM. Si Redis no
está disponible, se omite el marcado (el output-service asumirá ventana cerrada → plantilla).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class RedisWindowStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 86400, namespace: str = "wa:window") -> None:
        self._url = redis_url
        self._ttl = ttl_seconds
        self._ns = namespace
        self._client = None

    def _ensure(self):
        if self._client is None:
            import redis  # import perezoso
            self._client = redis.Redis.from_url(self._url)
        return self._client

    def mark(self, contact_ref: str) -> None:
        if not contact_ref:
            return
        try:
            self._ensure().setex(f"{self._ns}:{contact_ref}", self._ttl, "1")
        except Exception:
            log.warning("no se pudo abrir la ventana de 24h para %s (Redis no disponible)", contact_ref)
