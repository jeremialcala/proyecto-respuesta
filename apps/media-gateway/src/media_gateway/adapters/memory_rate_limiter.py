"""RateLimiter in-memory (tests). El real es `redis_rate_limiter` (INCR+EXPIRE por ventana).

Cuenta hits por clave en una ventana fija; `hit` devuelve False al superar `max_hits`. Sin TTL real
(es para tests); el adaptador Redis aporta la expiración por ventana.
"""
from __future__ import annotations


class MemoryRateLimiter:
    def __init__(self, max_hits: int = 1000) -> None:
        self._max = max_hits
        self._counts: dict[str, int] = {}

    def hit(self, key: str) -> bool:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] <= self._max
