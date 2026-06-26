# Contratos de API — Respuesta (esqueleto)

- **Fase AI-DLC:** 02-design
- **Estado:** draft
- **Especificaciones:** [`openapi.yaml`](openapi.yaml) (REST, OpenAPI 3.1) · [`asyncapi.yaml`](asyncapi.yaml) (eventos AMQP, AsyncAPI 2.6)

Toda la API exige autenticación (RS-01) y autorización por rol + scoping por clúster (RS-02). Las
entradas se validan por esquema (RS-04). Las transiciones de estado quedan auditadas (RS-06).

## Endpoints REST (síncronos)

| Método | Ruta | Descripción | AuthZ |
| :---- | :---- | :---- | :---- |
| `POST` | `/reports` | Crea un reporte (desaparecido/encontrado/autoreporte) con foto/ubicación | Acreditado o ciudadano |
| `GET` | `/entities/{id}` | Devuelve la entidad-persona y su estado (scope por rol) | Rol/clúster |
| `GET` | `/entities/{id}/cluster` | Conciencia de red: nº de buscadores (agregado anónimo) | Buscador del clúster |
| `POST` | `/entities/{id}/opt-in` | Buscador revela contacto al clúster (revocable) | Buscador |
| `POST` | `/candidates/{id}/confirm` | Coordinador confirma un candidato → match | Coordinador |
| `POST` | `/entities/{id}/state` | Transición de estado (según matriz de autoridad) | Rol según mecanismo |
| `POST` | `/proof-of-life/{id}` | Sube proof-of-life; devuelve link asegurado por login | Rescatista/persona |
| `GET` | `/proof-of-life/{id}` | Reproduce el video tras login (no compartible) | Clúster opt-in |
| `POST` | `/accreditations` | Acredita rescatista/coordinador (con autoridad) | Autoridad |
| `POST` | `/pfif/export` · `/pfif/import` | Federación PFIF | Sistema |

**Portal "mis reportes"** (auth Auth0/OAuth2, rol único — [ADR-0009](../00-project/adr/0009-dashboard-auth-auth0.md)):

| Método | Ruta | Descripción | AuthZ |
| :---- | :---- | :---- | :---- |
| `GET` | `/me/reports` | Lista los reportes propios del usuario | Usuario (Auth0) |
| `GET` | `/me/reports/{id}/timeline` | Timeline de eventos del reporte propio | Dueño |
| `POST` | `/me/reports/{id}/visibility` | Marca un reporte propio como público/privado | Dueño |
| `GET` | `/public/reports` | Lista reportes marcados como públicos | Usuario (Auth0) |

**Back office** (RBAC + firma — [ADR-0010](../00-project/adr/0010-back-office-roles-flujos.md)):

| Método | Ruta | Descripción | AuthZ |
| :---- | :---- | :---- | :---- |
| `POST` | `/candidates/{id}/resolve` | Resuelve match manual (MATCHED/DISCARDED) con justificación + firma | Coordinador |
| `POST` | `/rescuers/{id}/certify` | Transición de certificación de rescatista (PENDING→CERTIFIED/REJECTED/REVOKED) | Coordinador/Autoridad |
| `POST` | `/authorities` | Alta de autoridad en la cadena de confianza (cascada) | ADMIN / Celda regional |
| `POST` | `/entities/{id}/release-info` | Autoriza notificación de información delicada (firma) | Autoridad |

## Webhooks de entrada

| Origen | Ruta | Descripción |
| :---- | :---- | :---- |
| Redes de mensajería | `POST /webhooks/{red}` | Mensajes entrantes (WhatsApp/IG/Messenger/Telegram); pasan por rieles |

## Eventos (asíncronos, AMQP — patrón cola+worker)

Todos los eventos adoptan el **sobre común** ([ADR-0011](../00-project/adr/0011-contrato-eventos.md)):
`event_id`, `event_type` (`dominio.evento`), `producer`, `timestamp`, `version` (semver), `payload`.
Cuerpos con PII/biométrico en JWE; el embedding no viaja inline (referencia a pgvector).

| Evento | Productor → Consumidor | Descripción |
| :---- | :---- | :---- |
| `report.received` | Intake → Cola | Reporte encolado (offline-first) |
| `report.ingested` | Worker → Matching | Adjuntos en almacén protegido; listo para resolver |
| `candidate.generated` | Matching → Back office | Candidato con score; enruta por umbral |
| `match.confirmed` | Coordinador/Sistema → Notificación | Match confirmado (humano ≥65 % o autoreporte 100 %) |
| `match.resuelto` | Back office → Notificación + Auditoría | Resolución manual del coordinador (MATCHED/DISCARDED) con firma (ADR-0010) |
| `state.changed` | API → Notificación + Auditoría | Transición de estado (auditada) |
| `notification.sent` | Notificación → Canal | Notificación entregada al clúster opt-in |

> **Catálogo canónico (ADR-0011):** `reporte.creado` (≈ `report.received`/`report.ingested`),
> `match.evaluado` (≈ `candidate.generated`), `match.resuelto` (nuevo), `notificacion.estado_cambiado`
> (≈ `state.changed`/`notification.sent`). La unificación de nombres (ES vs EN) es decisión abierta en
> ADR-0011.

## Especificaciones formales

- **REST:** [`openapi.yaml`](openapi.yaml) — OpenAPI 3.1, 11 endpoints, 15 esquemas, seguridad
  bearer/JWT (RS-01), errores RFC 7807 (RS-04), rate limit 429 (RS-05).
- **Eventos:** [`asyncapi.yaml`](asyncapi.yaml) — AsyncAPI 2.6, 6 canales AMQP (`report.received` …
  `notification.sent`), payload del candidato alineado al motor (ADR-0004).

## Pendiente

- `<TODO>` Linting de specs en CI (Spectral/openapi-spec-validator) — fase 05-deployment.
- `<TODO>` Versionado y publicación del contrato (consumer-driven) en fase 04-testing.
