# matching-worker

Motor de matching de Respuesta (worker). Implementa el pipeline de [ADR-0004](../../docs/00-project/adr/0004-motor-de-matching.md):
mapeo facial (OpenCV YuNet + SFace), almacenamiento **pgvector** + índice **FAISS HNSW**, tolerancia
a **drift de edad** y **fusión multi-señal**.

## Arquitectura (Clean Architecture / DDD)

```
src/matching_worker/
├── domain/        # lógica pura, testeada: drift, fusion, quality, tracking, models
├── application/   # ports (interfaces) + matching_service (caso de uso)
├── adapters/      # infraestructura (esqueletos): opencv, pgvector, faiss, amqp
└── config.py      # parámetros (τ0, M/efSearch, umbrales) — se calibran en fase 04
```

Regla de dependencia: hacia adentro. El dominio no conoce infraestructura.

**Invariante de seguridad (probado en tests):** el face-match **nunca** auto-confirma; el drift y
los menores **empujan a coordinador**. Solo el autoreporte (100 %) es automático.

## Estado

- ✅ Dominio puro implementado y cubierto por tests (drift, fusión, calidad, tracking).
- ✅ Caso de uso `MatchingService` con tests de integración (fakes).
- 🚧 Adaptadores (OpenCV/pgvector/FAISS/AMQP) en esqueleto — `NotImplementedError`, fase 03.

## Tests

```bash
pip install -e ".[test]"   # o: pip install pytest
pytest
```

Los tests del dominio y del servicio pasan sin infraestructura. Los adaptadores se prueban en
fase 03 con sus dependencias reales.
