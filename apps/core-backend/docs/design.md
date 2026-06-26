# Diseño — core-backend

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0007](../../../docs/00-project/adr/0007-esquema-reporte-retencion-auditoria.md)
  (esquema/retención/auditoría) · [ADR-0011](../../../docs/00-project/adr/0011-contrato-eventos.md)
  (eventos) · [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) (SQS/SNS) ·
  charter (matriz de transiciones)
- **Vista C4:** [c4-container](../../../docs/architecture/c4-container.md) (API/Backend + almacenes)

## Flujos

**Intake** (worker): consume `report.received` → `validate_report` (núcleo obligatorio) → asigna
`report_id`/`entity_id` → persiste (esquema dinámico) → **auditoría encadenada** → publica
`report.ingested`. Reportes inválidos → auditados y descartados.

**Estado** (API `/entities/{id}/state`): `can_transition` (matriz de autoridad) → `fallecido` exige
evidencia → persiste → auditoría → publica `state.changed`. Denegaciones se auditan (`state.denied`).

**Reporte** (API `/reports`): misma lógica de dominio que el worker.

## Invariantes (cubiertos por tests)

- Auditoría: cadena SHA-256 verificable; alterar un registro la rompe (`verify_chain`).
- `fallecido`/`localizado_critico` solo por autoridad; autorreporte solo `a_salvo`.
- `fallecido` sin evidencia → rechazado.
- Reporte sin núcleo obligatorio → no se ingesta.

## Pendiente (fase 03/04)

- Resolución/merge de entidades (lo hace matching); correlación texto↔media para `report.ingested`.
- Auth (Auth0/JWT) + RBAC por rol/clúster; índices JSONB; borrado por retención (ADR-0007).
