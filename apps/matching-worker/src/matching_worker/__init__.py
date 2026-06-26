"""Motor de matching de Respuesta (worker).

Clean Architecture / DDD:
- `domain`      — lógica pura (drift, fusión, calidad, tracking). Sin dependencias de infraestructura.
- `application` — puertos (interfaces) y casos de uso (MatchingService).
- `adapters`    — infraestructura (OpenCV, FAISS, pgvector, AMQP). Esqueletos.

Decisiones: ADR-0004 (motor de matching). Regla invariante: el face-match NUNCA confirma solo;
solo el autoreporte (100 %) es automático. El drift amplía candidatos pero empuja a coordinador.
"""

__version__ = "0.1.0"
