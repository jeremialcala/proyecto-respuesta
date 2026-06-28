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
├── application/   # ports + matching_service + enrollment_service (ADR-0016) + inference_service (ADR-0019)
├── adapters/      # arcface, sqs_consumer, sqs_sns_event_bus, pgvector, faiss,
│                  #   vault_media_gateway (S3/MinIO), pg_pending_enrollment_store, http_grant_revoker,
│                  #   pg_processed_event_store (idempotencia, ADR-0018),
│                  #   remote_face_extractor + sqs_request_reply (extractor remoto, ADR-0019)
├── inference_main.py  # entrypoint del PLANO DE INFERENCIA (imagen `Dockerfile.inference`, ADR-0019)
└── config.py      # parámetros (τ0, M/efSearch, umbrales) — se calibran en fase 04
```

**Dos imágenes:** `Dockerfile` (worker de control, in-region) y `Dockerfile.inference` (plano de
inferencia stateless, ADR-0019). El segundo reusa el mismo paquete (DRY) con otro entrypoint.

Regla de dependencia: hacia adentro. El dominio no conoce infraestructura.

**Invariante de seguridad (probado en tests):** el face-match **nunca** auto-confirma; el drift y
los menores **empujan a coordinador**. Solo el autoreporte (100 %) es automático.

**Plano GPU dedicado + idempotencia ([ADR-0018](../../docs/00-project/adr/0018-desacople-gpu-llm-facematch.md)):**
el facematch corre en un pool GPU **separado del LLM** (manifiestos en `deploy/k8s/`, `nodeSelector`/
taint `respuesta.io/gpu-pool=facematch` + anti-afinidad). El consumo es **idempotente por `event_id`**
(`PgProcessedEventStore`): SQS entrega *at-least-once*, así que un redelivery (pod que muere, GPU
reclamada, visibility timeout vencido) se descarta sin re-enrolar ni re-preguntar — el `event_id` se
marca **tras** procesar con éxito, preservando el redrive a DLQ cuando algo falla.

**Plano de inferencia portable ([ADR-0019](../../docs/00-project/adr/0019-imagen-inferencia-arcface-tensorrt-vastai.md)):**
la extracción de embedding (GPU) se separa en una **imagen stateless dedicada** (`Dockerfile.inference`,
`inference_main`) que consume `face.extract.requested` y devuelve `face.embedded` con **solo el vector
512-d** — sin DB/Vault/secretos; la galería/índice viven en-región. El worker in-region elige extractor
por config (`FACE_EXTRACTOR=local|remote`); en `remote`, `RemoteFaceExtractor`+`SqsRequestReplyClient`
hacen request-reply por el bus (timeout → redrive idempotente). El destino del plano remoto (EKS/on-prem/
vast.ai Secure Cloud) es **configuración**. Egress real a terceros gated por validación legal + PoC.

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
