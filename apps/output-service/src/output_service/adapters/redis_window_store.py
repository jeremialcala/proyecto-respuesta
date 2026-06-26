"""Ventana de servicio de 24h por contacto sobre Redis. `redis` perezoso.

La marca la pone la ingestión (gateway/meta-handler) al recibir un mensaje del usuario, con TTL 24h.
Aquí solo se consulta si la clave existe. Si Redis no está disponible, se asume **cerrada** (seguro:
fuerza plantilla HSM en vez de arriesgar un texto rechazado por Meta).
"""
from __future__ import annotations


class RedisWindowStore:
    def __init__(self, redis_url: str, namespace: str = "wa:window") -> None:
        self._url = redis_url
        self._ns = namespace
        self._client = None

    def _ensure(self):
        if self._client is None:
            import redis
            self._client = redis.Redis.from_url(self._url)
        return self._client

    def is_open(self, contact_ref: str) -> bool:
        try:
            return bool(self._ensure().exists(f"{self._ns}:{contact_ref}"))
        except Exception:
            return False
