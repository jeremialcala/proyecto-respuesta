# matching-worker

Motor de matching de Respuesta (worker). Implementa el pipeline de [ADR-0004](../../docs/00-project/adr/0004-motor-de-matching.md):
mapeo facial **ArcFace/IResNet100 (512-d)** ([ADR-0013](../../docs/00-project/adr/0013-arcface-scoring-solo-rostro.md)),
almacenamiento **pgvector** + índice **FAISS HNSW (d=512)**, tolerancia a **drift de edad** y, en MVP,
**scoring solo-rostro**. Además, el **enrolamiento biométrico y la desambiguación multi-rostro**
([ADR-0016](../../docs/00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md), ver
[docs/enrollment-disambiguation.md](docs/enrollment-disambiguation.md)). Transporte **AWS SQS/SNS**
([ADR-0012](../../docs/00-project/adr/0012-broker-aws-sqs-sns.md)).

## Arquitectura (Clean Architecture / DDD)

```
src/matching_worker/
├── domain/        # lógica pura, testeada: drift, fusion, quality, tracking, models (BBox, PendingEnrollment)
├── application/   # ports + matching_service + enrollment_service (enrolamiento/desambiguación, ADR-0016)
├── adapters/      # arcface, sqs_consumer, sqs_sns_event_bus, pgvector, faiss,
│                  #   vault_media_gateway (S3/MinIO), pg_pending_enrollment_store, http_grant_revoker
└── config.py      # parámetros (τ0, M/efSearch, umbrales) — se calibran en fase 04
```

Regla de dependencia: hacia adentro. El dominio no conoce infraestructura.

**Invariante de seguridad (probado en tests):** el face-match **nunca** auto-confirma; el drift y
los menores **empujan a coordinador**. Solo el autoreporte (100 %) es automático.

## Estado

- ✅ Dominio puro implementado y cubierto por tests (drift, fusión, calidad, tracking).
- ✅ Caso de uso `MatchingService` con tests de integración (fakes).
- ✅ Sobre de eventos (`application/events`) y payload `candidate.generated` alineados a ADR-0011 (tests).
- 🚧 Adaptadores ArcFace/SQS/SNS/pgvector/FAISS implementados con deps perezosas; afinado y pruebas con infra real en fase 03 (GPU RTX 3090 — ADR-0001/0006).

## Tests

```bash
pip install -e ".[test]"   # o: pip install pytest
pytest
```

Los tests del dominio y del servicio pasan sin infraestructura. Los adaptadores se prueban en
fase 03 con sus dependencias reales.
