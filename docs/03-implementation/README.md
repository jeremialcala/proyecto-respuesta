# Fase 03 — Implementation

Red-Green-Refactor-**Secure**, prompting seguro, controles de riesgos de IA, doble revisión (IA + humano).

**Gate 2 (cierre):** SAST limpio + dependencias verificadas (SCA, lockfiles) + 80 % de cobertura.

## Estado de la implementación

Flujo central del MVP implementado **test-first** en `apps/` (Clean Architecture/DDD, **174 tests
unitarios en verde**), container-ready (ADR-0014):

- **Ingestión Meta**: `webhook-gateway` (firma + idempotencia → `meta.received`), `meta-handler`
  (normaliza texto/imagen y **respuestas interactivas** → `inbound.text`/`inbound.media`),
  `vault-worker` (escaneo AV/CSAM + cifrado de sobre → `media.stored`).
- **Canal principal**: `chatbot-gateway` (rieles + LLM on-prem no autoritativo + memoria pgvector +
  desambiguación → `outbound.reply`/`report.received`/`face.disambiguation.resolved`) y `output-service`
  (Graph API: texto / plantilla HSM + **imagen y botón de opciones** para la desambiguación).
- **Entrega de medios**: `media-gateway` (ADR-0017) — única salida pública de medios por **URL firmada**
  (dos planos: público `GET /m/{token}`, interno `POST /grants`).
- **Núcleo**: `core-backend` (API + reportes/estados + **auditoría SHA-256** → `report.ingested`/
  `state.changed`) y `matching-worker` (**ArcFace 512-d** + **enrolamiento/desambiguación** ADR-0016 →
  `entity.enrolled`/`enrollment.failed`/`face.disambiguation.requested`).

Cada servicio usa deps perezosas en los adaptadores; los tests cubren dominio y casos de uso sin
infraestructura. Pendientes de endurecimiento (placeholders explícitos): JWE real con Vault (ADR-0008),
descifrado de la bóveda en el matcher (en dev se usa **cipher passthrough + MinIO** persistente),
ClamAV + hashes CSAM (ADR-0005), rieles NeMo con modelo guardián (ADR-0002) y la traza Event/EventAction.

**Gate 2 (cierre):** SAST limpio + SCA/lockfiles + cobertura objetivo + afinado con infra real.
Hereda los controles RS-xx del PRD y las decisiones de los **ADR-0001…0017**.
