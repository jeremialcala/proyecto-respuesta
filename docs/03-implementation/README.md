# Fase 03 — Implementation

Red-Green-Refactor-**Secure**, prompting seguro, controles de riesgos de IA, doble revisión (IA + humano).

**Gate 2 (cierre):** SAST limpio + dependencias verificadas (SCA, lockfiles) + 80 % de cobertura.

## Estado de la implementación

Flujo central del MVP implementado **test-first** en `apps/` (Clean Architecture/DDD, **99 tests
unitarios en verde**), container-ready (ADR-0014):

- **Ingestión Meta**: `webhook-gateway` (firma + idempotencia → `meta.received`), `meta-handler`
  (normaliza → `inbound.text`/`inbound.media`), `vault-worker` (escaneo AV/CSAM + cifrado de sobre →
  `media.stored`).
- **Canal principal**: `chatbot-gateway` (rieles + LLM on-prem no autoritativo → `outbound.reply`/
  `report.received`) y `output-service` (Graph API: texto / plantilla HSM).
- **Núcleo**: `core-backend` (API + reportes/estados + **auditoría SHA-256** → `report.ingested`/
  `state.changed`) y `matching-worker` (**ArcFace 512-d** → `candidate.generated`).

Cada servicio usa deps perezosas en los adaptadores; los tests cubren dominio y casos de uso sin
infraestructura. Pendientes de endurecimiento (placeholders explícitos): JWE real con Vault (ADR-0008),
ClamAV + hashes CSAM (ADR-0005), rieles NeMo con modelo guardián (ADR-0002), persistencia real
Postgres/pgvector/FAISS y la traza Event/EventAction.

**Gate 2 (cierre):** SAST limpio + SCA/lockfiles + cobertura objetivo + afinado con infra real.
Hereda los controles RS-xx del PRD y las decisiones de los **ADR-0001…0014**.
