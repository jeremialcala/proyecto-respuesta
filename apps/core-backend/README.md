# core-backend

Orquestador del flujo central de Respuesta. Es la **fuente de verdad** de reportes, entidades y
estados (Postgres), con **auditoría append-only SHA-256** (ADR-0007). Expone la **API REST** y
consume `report.received`; emite `report.ingested` (→ matching) y `state.changed` (→ notificación).

## Responsabilidades

- **Reportes** (esquema dinámico, ADR-0007): núcleo obligatorio (nombre, tipo y nº de id) +
  `attributes` extensibles sin migración. Valida y asigna `report_id`/`entity_id`.
- **Máquina de estados** (charter): transiciones por **matriz de autoridad** —`fallecido` y
  `localizado_critico` solo por autoridad; `fallecido` exige evidencia. El sistema **transmite**, no
  deduce.
- **Auditoría SHA-256 encadenada**: cada operación sensible (creación, transición, rechazo, denegación)
  se registra y la cadena es **verificable** (`verify_chain`) — no repudio (RS-06).
- **Eventos**: `report.ingested` dispara el matching; `state.changed` alimenta notificación/auditoría.

## Arquitectura (Clean Architecture / DDD)

```
src/core_backend/
├── domain/        # puro: audit (hash chain), state_machine (matriz), report (validación), models
├── application/   # ports + chained_audit + intake_service + state_service + events
├── adapters/      # sqs_consumer, sns_publisher, pg_stores, memory_stores
├── api/           # app.py (FastAPI: /reports, /entities/{id}/state, /healthz)
└── config.py
```

## MVP / pendiente fase 03

- **Resolución de entidades**: el intake crea una entidad **provisional**; el merge/colisión lo hace
  el motor de matching (RF-11).
- Correlación `report.received` (texto) ↔ `media.stored` (foto) para enriquecer `report.ingested`.
- Auth (Auth0/JWT, ADR-0009), rate-limit y RBAC por rol/clúster (RS-01/02) en el edge/API.
- Anclaje externo opcional de la cadena de auditoría (RFC 3161) — ADR-0007.

## Estado

- ✅ Dominio (auditoría/estados/reporte) + servicios con **16 tests en verde** (memoria + fakes).
- 🚧 Adaptadores Postgres/SQS/SNS con deps perezosas; persistencia real e índices JSONB en fase 03.

## Ejecutar

```bash
pip install -e ".[test]" && pytest
pip install -e . && uvicorn core_backend.api.app:app --port 8080   # API
pip install -e . && python -m core_backend                          # consumidor report.received
```
