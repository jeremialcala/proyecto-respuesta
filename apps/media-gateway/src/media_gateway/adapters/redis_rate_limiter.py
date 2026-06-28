"""Rate-limit por ventana fija sobre Redis (INCR + EXPIRE). `redis` perezoso (ADR-0017 §6).

`hit(key)` cuenta la descarga dentro de la ventana actual; devuelve False al superar `max_hits`. La
clave se namespacea; el primer INCR de la ventana fija el TTL. El llamador pasa la clave por token;
límites por IP/global se componen con varias instancias o claves.
"""
from __future__ import annotations


class RedisRateLimiter:
    def __init__(self, redis_url: str, max_hits: int, window_seconds: int,
                 namespace: str = "media:rl") -> None:
        self._url = redis_url
        self._max = max_hits
        self._window = window_seconds
        self._ns = namespace
        self._client = None

    def _ensure(self):
        if self._client is None:
            import redis  # import perezoso
            self._client = redis.Redis.from_url(self._url)
        return self._client

    def hit(self, key: str) -> bool:
        client = self._ensure()
        k = f"{self._ns}:{key}"
        count = client.incr(k)
        if count == 1:
            client.expire(k, self._window)
        return int(count) <= self._max
