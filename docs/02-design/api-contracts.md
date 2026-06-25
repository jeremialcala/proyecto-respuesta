# Contratos de API — Respuesta (esqueleto)

- **Fase AI-DLC:** 02-design
- **Estado:** draft (detalle OpenAPI/AsyncAPI pendiente)

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

## Webhooks de entrada

| Origen | Ruta | Descripción |
| :---- | :---- | :---- |
| Redes de mensajería | `POST /webhooks/{red}` | Mensajes entrantes (WhatsApp/IG/Messenger/Telegram); pasan por rieles |

## Eventos (asíncronos, AMQP — patrón cola+worker)

| Evento | Productor → Consumidor | Descripción |
| :---- | :---- | :---- |
| `report.received` | Intake → Cola | Reporte encolado (offline-first) |
| `report.ingested` | Worker → Matching | Adjuntos en almacén protegido; listo para resolver |
| `candidate.generated` | Matching → Back office | Candidato con score; enruta por umbral |
| `match.confirmed` | Coordinador/Sistema → Notificación | Match confirmado (humano ≥65 % o autoreporte 100 %) |
| `state.changed` | API → Notificación + Auditoría | Transición de estado (auditada) |
| `notification.sent` | Notificación → Canal | Notificación entregada al clúster opt-in |

## Pendiente

- `<TODO>` Especificación OpenAPI 3.1 de los endpoints REST.
- `<TODO>` Especificación AsyncAPI de los eventos.
- `<TODO>` Esquemas de request/response y códigos de error (alineados a RS-04, RS-14).
