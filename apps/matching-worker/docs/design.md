# Diseño — matching-worker

- **Fase AI-DLC:** 03-implementation (esqueleto, test-first)
- **Decisión base:** [ADR-0004](../../../docs/00-project/adr/0004-motor-de-matching.md) (enmendada por [ADR-0013](../../../docs/00-project/adr/0013-arcface-scoring-solo-rostro.md): ArcFace 512-d, scoring solo-rostro; [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md): SQS/SNS)
- **Vista C4:** [c4-component-matching](../../../docs/architecture/c4-component-matching.md)

## Pipeline

1. **Ingesta** (`report.ingested` vía **AWS SQS**) → `FaceMapper` (**ArcFace/IResNet100**: detector
   SCRFD + embedding 512-d por persona; en video, tracking + Hierarchical Windowing).
2. **Compuerta de calidad** descarta rostros pobres.
3. **Reporte de desaparecido:** los embeddings de referencia se guardan en **pgvector** (verdad).
4. **Foto/video de rescatista:** se busca en el **índice FAISS HNSW** (refrescado desde pgvector).
5. **Banda por drift** (`domain/drift.py`) → ruteo: descarte / coordinador / fusión.
6. **Fusión** (`domain/fusion.py`) → confianza → evento `candidate.generated` con **sobre estándar**
   (ADR-0011) publicado en **SNS**. En MVP el scoring es **solo-rostro** (geo/text peso 0 — ADR-0013).

## Invariantes (cubiertos por tests)

- El face-match nunca auto-confirma (`Routing.FUSE` no es auto-confirmación; el umbral global vive
  en el flujo central). Drift tolerado y menores → `COORDINATOR`.
- Agrupación por track más estricta (`reid_distance < tau0`).
- Pesos de fusión dinámicos: una señal ausente no rompe el score.

## Pendiente (fase 03/04)

- Afinar adaptadores con infra real (ArcFace en GPU, SQS/SNS, pgvector, FAISS); `__main__` ya cablea.
- Recalibrar `τ0`/`α/β/Δ_max` **para ArcFace** y umbrales de tracking con datos reales (fase 04).
- Resolver el embedding del probe desde `media_ref` (descarga + FaceMapper) en el consumidor SQS.
- Cadencia de refresco del índice FAISS (d=512) desde pgvector.
