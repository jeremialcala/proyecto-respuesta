# Diseño — matching-worker

- **Fase AI-DLC:** 03-implementation (esqueleto, test-first)
- **Decisión base:** [ADR-0004](../../../docs/00-project/adr/0004-motor-de-matching.md)
- **Vista C4:** [c4-component-matching](../../../docs/architecture/c4-component-matching.md)

## Pipeline

1. **Ingesta** (`report.ingested` vía AMQP) → `FaceMapper` (OpenCV YuNet detecta rostros, SFace
   genera el embedding por persona; en video, tracking + Hierarchical Windowing).
2. **Compuerta de calidad** descarta rostros pobres.
3. **Reporte de desaparecido:** los embeddings de referencia se guardan en **pgvector** (verdad).
4. **Foto/video de rescatista:** se busca en el **índice FAISS HNSW** (refrescado desde pgvector).
5. **Banda por drift** (`domain/drift.py`) → ruteo: descarte / coordinador / fusión.
6. **Fusión multi-señal** (`domain/fusion.py`) → confianza → evento `candidate.generated`.

## Invariantes (cubiertos por tests)

- El face-match nunca auto-confirma (`Routing.FUSE` no es auto-confirmación; el umbral global vive
  en el flujo central). Drift tolerado y menores → `COORDINATOR`.
- Agrupación por track más estricta (`reid_distance < tau0`).
- Pesos de fusión dinámicos: una señal ausente no rompe el score.

## Pendiente (fase 03/04)

- Implementar adaptadores (OpenCV, pgvector, FAISS, AMQP) y el wiring en `__main__`.
- Calibrar `τ0`, `α/β/Δ_max`, pesos de fusión y umbrales de tracking con datos reales.
- Cadencia de refresco del índice FAISS desde pgvector.
