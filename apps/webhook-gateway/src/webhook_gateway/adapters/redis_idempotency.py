"""Guarda de idempotencia sobre Redis (SET NX + TTL). `redis` se importa de forma perezosa."""
from __future__ import annotations


class RedisIdempotencyStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 86400, namespace: str = "meta:idem") -> None:
        self._url = redis_url
        self._ttl = ttl_seconds
        self._ns = namespace
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import redis  # import perezoso
            self._client = redis.Redis.from_url(self._url)
        return self._client

    def seen(self, key: str) -> bool:
        client = self._ensure_client()
        # SET key 1 NX EX ttl → devuelve True si se creó (no existía). Duplicado = no se creó.
        created = client.set(f"{self._ns}:{key}", "1", nx=True, ex=self._ttl)
        return not bool(created)
