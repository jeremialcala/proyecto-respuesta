# ADR-0015: Memoria de conversación del chatbot (estado por contacto, Postgres+pgvector)

- **Estado:** accepted
- **Fecha:** 2026-06-27
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design / 03-implementation
- **Controles OWASP afectados:** A01 (control de acceso entre conversaciones), A04 (datos sensibles), A09 (auditoría/retención)
- **Relacionado:** RF-04/07, [ADR-0001](0001-llm-on-premises.md) (LLM on-prem), [ADR-0002](0002-nemo-guardrails-prompt-injection.md) (rieles), [ADR-0006](0006-residencia-sao-paulo.md) (residencia), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md) (retención), [ADR-0008](0008-boveda-llaves-identidad.md) (identidad), [ADR-0011](0011-contrato-eventos.md) (eventos), [ADR-0013](0013-arcface-scoring-solo-rostro.md) (pgvector ya en uso)

## Contexto

La Pasarela de Chatbot era **sin estado**: cada `inbound.text` se procesaba aislado, el LLM recibía
solo el texto del mensaje actual y lo único que identificaba al interlocutor era el `contact_ref`
opaco. Esto rompe el **control de reportes**: un reporte rara vez llega completo en un solo mensaje
(el nombre en un turno, el documento en otro), y el bot volvía a pedir datos ya dados o no podía
cerrar la captura. El `design.md` lo listaba como pendiente: *"manejo de conversación multi-turno
(estado por contacto)"*.

Necesitamos que el chatbot (1) sepa **quién nos habla** de forma estable, (2) tenga **contexto de la
conversación** que está teniendo y (3) **acceda a los datos de esa conversación específica** para
acumular el reporte. Con una restricción de costo: reenviar todo el historial al LLM en cada turno
crece linealmente en tokens y latencia sobre la RTX 3090 (ADR-0001).

## Decisión

**1. Identidad estable y no reversible.** `conversation_key = sha256(bot_id | channel | contact_ref)`.
Es la clave de sesión; el handle crudo (teléfono/PSID) **no** se usa como clave ni se persiste en
claro en esta capa.

**2. Perfil de sesión (estado por contacto).** Por cada `conversation_key` se guarda un
`SessionProfile`: lo que el interlocutor declara (nombre, intención) y el **borrador del reporte
acumulado** (sujeto, tipo y nº de documento, notas), más `turn_count` y `report_emitted`. El control
de reportes opera sobre el **perfil acumulado**, no sobre el turno suelto: `report.received` se
publica una sola vez, cuando el núcleo (intención + nombre + tipo + nº id) queda completo a lo largo
de la conversación.

**3. Memoria con recuperación semántica (economía del LLM).** Los turnos se guardan en Postgres con
su **embedding** (`pgvector`, modelo on-prem `nomic-embed-text`, 768 dims). En cada turno el contexto
que recibe el LLM es: resumen compacto del perfil (system) + **ventana reciente** (últimos N turnos,
coherencia) + **top-k turnos antiguos** recuperados por similitud coseno (`<=>`) con el mensaje
actual. Así traemos solo lo pertinente en vez de todo el historial → prompt acotado y barato.

**4. Puertos y degradación elegante.** `ConversationStore` y `Embedder` son puertos
(hexagonal). Adaptadores: `PgConversationStore` (prod) y `MemoryConversationStore` (dev/tests);
`OllamaEmbedder` y `NullEmbedder`. Sin DSN → memoria; sin modelo de embeddings o si el embedder
falla → memoria solo con ventana reciente (nunca rompe la conversación).

**5. El LLM sigue sin ser autoritativo (ADR-0001).** La memoria no cambia estados ni decide matches;
solo conversa y captura.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
|---|---|---|---|
| A. Sin estado (actual) | Simple | No completa reportes multi-turno; re-pregunta | Bajo |
| B. Historial completo al LLM cada turno | Fácil | Costo/latencia lineal; supera ventana de contexto | Fuga si se mezclan conversaciones |
| **C. Pg+pgvector: perfil + ventana reciente + top-k semántico (elegida)** | Económico; reaprovecha pgvector (ADR-0013); residente en São Paulo (ADR-0006) | Más piezas (embedder, tablas) | Aislamiento por `conversation_key`; retención acotada |
| D. Redis con TTL | Expiración nativa | Otra infra de estado; sin recuperación semántica | Menos auditable |

## Consecuencias

- **Positivas:** reportes completados de forma incremental; el bot no re-pregunta; prompts pequeños
  y baratos; reutiliza la infra `pgvector` ya presente; aislamiento estricto entre conversaciones.
- **Negativas / deuda asumida:** se añade un modelo de embeddings on-prem y dos tablas
  (`chat_sessions`, `chat_turns`); `psycopg` como dependencia (import perezoso); afinado pendiente de
  N (ventana) y k (recuperación).
- **Impacto en threat model:** nueva superficie de datos de conversación (PII de contacto) →
  mitigada por clave hash, residencia São Paulo (ADR-0006), retención con purga por edad
  (`purge_older_than`, alineado a ADR-0007) y control de acceso por `conversation_key` (A01). El
  riel de salida (ADR-0002) sigue evitando fuga de datos de **otras** conversaciones.

## Pendiente

- Job programado de retención (`purge_older_than`) y su ventana exacta (alinear con ADR-0007).
- Resolución a **identidad verificada** (parentesco/gobierno, ADR-0009) sobre el perfil de sesión.
- Resumen/compactación del perfil cuando la conversación es muy larga (summary rolling).
