# ADR-0007: Esquema dinámico del reporte, retención y auditoría append-only (SHA-256)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A04 (data), A08 (integridad de datos), A09 (logging/no repudio), A02 (cripto)
- **Relacionado:** RF-03, RF-13, RS-06, RS-07, AB-08, AB-10, threat model T10/T11, [ADR-0003](0003-hosting-modelo-a.md)/[ADR-0006](0006-residencia-sao-paulo.md), [ADR-0004](0004-motor-de-matching.md), [ADR-0008](0008-boveda-llaves-identidad.md)

## Contexto

El reporte de desaparecido es el dato de entrada del flujo central (RF-03). En una emergencia, la
información llega **incompleta y heterogénea**: a veces solo un nombre, a veces foto + ubicación +
notas médicas. Forzar un esquema rígido perdería reportes válidos; un esquema sin mínimos haría
imposible el matching y la deduplicación. Además, dos requisitos no funcionales pesan fuerte:
**retención GDPR** (RS-07: borrado al cierre de la emergencia + 12 meses) y **no repudio** de toda
operación sobre datos sensibles (RS-06, AB-10), porque mover un estado o fusionar entidades son
acciones de alto costo (T10/T11).

## Decisión

**1. Esquema dinámico del reporte con un núcleo obligatorio.**

- **Campo obligatorio:** `nombre_completo`.
- **Campos opcionales:** `tipo_identificacion` y `numero_identificacion` (**documento opcional** —
  revisado por ADR-0016/0020: quien reporta a un tercero rara vez tiene su cédula y la identidad del
  sistema es **biométrica**, no el número), `foto` (medio en bóveda — ADR-0005/0008), `ultima_ubicacion`
  (coordenada **o** dirección de texto), `notas_generales` (texto libre, p. ej. dolencias crónicas,
  medicamentos requeridos — dato de salud, categoría especial GDPR Art. 9).
- **Accionabilidad** (cuándo el reporte dispara enrolamiento/cierre): además del nombre, requiere al
  menos **una pista localizable** — una **foto** o la **última ubicación**. Se exige en la capa
  conversacional (chatbot-gateway); el intake del core solo valida el nombre.
- El resto de atributos se modela como **pares clave-valor extensibles** por tipo de reporte, sin
  migración de esquema cuando aparece un atributo nuevo. La **máquina de estados** del charter (no
  el esquema) gobierna el ciclo de vida.

**2. Almacenamiento: Postgres + pgvector** (consolidado con ADR-0004). Postgres es la fuente de
verdad de reportes, entidades, estados y parentesco; **pgvector** guarda los embeddings (fuente de
verdad de los biométricos derivados); FAISS es el índice ANN derivado (ADR-0004). La foto original
vive cifrada en la bóveda de medios (ADR-0005/0008); el reporte solo guarda su `media_ref`.

**3. Retención y borrado** (consolidado con `data-classification.md`). El borrado de datos
Restringidos (biométricos, ubicaciones, registro de fallecimiento) se gatilla por el **cierre de la
emergencia indicado por el coordinador + 12 meses**. El plazo es **diferible por el coordinador**
(con registro auditable del diferimiento). El borrado se ejecuta automáticamente al cumplirse el
plazo vigente.

**4. Auditoría append-only con encadenamiento SHA-256.** Toda operación sobre datos sensibles
(creación/edición de reporte, transición de estado, match manual, acceso en claro por coordinador,
diferimiento de retención, borrado) se registra en una **tabla inmutable append-only**. Cada fila
incluye `hash = SHA-256(payload_canónico || hash_fila_anterior)`, formando una **cadena verificable**
(estilo hash chain): alterar o borrar una fila rompe la cadena y es detectable. La tabla no admite
`UPDATE` ni `DELETE` a nivel de aplicación; las correcciones se hacen con nuevas filas (compensación).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Esquema dinámico (núcleo + KV) en Postgres + pgvector** ✅ | Captura reportes incompletos sin perder datos; extensible sin migración; un solo motor relacional + vectorial (alinea ADR-0004) | KV débilmente tipado → validar en aplicación; consultas sobre atributos dinámicos menos eficientes | Validación de esquema obligatoria en intake (A04/A05) |
| **B. Esquema relacional rígido** | Tipado fuerte, consultas simples | Pierde reportes incompletos; cada atributo nuevo = migración; frágil en emergencia | Rechazo de datos válidos → pérdida operativa |
| **C. Documental puro (Mongo)** | Máxima flexibilidad de esquema | Pierde transaccionalidad e integración con pgvector; dos motores | Borrado/consistencia más difíciles de garantizar (RS-07) |
| **Auditoría: log de aplicación normal** | Simple | Mutable → no garantiza no repudio (AB-10) | Repudio/manipulación de la traza (A09/A08) |
| **Auditoría: append-only + hash chain (SHA-256)** ✅ | No repudio verificable; manipulación detectable; barato | No es un ledger distribuido (confianza en el operador del store) | Mitiga T11; cubre RS-06 |

## Consecuencias

- **Positivas:** se capturan reportes parciales sin perder señal; el modelo evoluciona sin
  migraciones; un único motor (Postgres+pgvector) sostiene datos y embeddings; la retención cumple
  GDPR/RS-07 con control del coordinador; la auditoría append-only con SHA-256 da **no repudio
  verificable** (RS-06) y hace **detectable** cualquier manipulación (A08), cubriendo AB-08/AB-10 y
  reforzando T10/T11.
- **Negativas / deuda asumida:** los atributos KV exigen **validación estricta en la aplicación**
  (no la da el esquema); las consultas sobre atributos dinámicos son menos eficientes (mitigable con
  índices GIN/JSONB); la hash chain da integridad pero **no es un ledger distribuido** — la confianza
  recae en el operador (aceptable bajo Modelo A); el borrado por retención debe **conciliarse con la
  inmutabilidad** de la auditoría (se borra el dato sensible, se conserva el registro seudonimizado
  del evento de borrado).
- **Impacto en threat model:**
  - **A08 / T10 (merge erróneo/manipulación):** la cadena SHA-256 hace detectable cualquier
    alteración del histórico; el merge sigue siendo reversible (RF-11).
  - **A09 / T11 (repudio):** cada operación queda atada a actor + timestamp + hash encadenado.
  - **A04 / RS-07:** minimización (solo núcleo obligatorio) y borrado por retención con diferimiento
    auditado.

## Decisiones abiertas

- `<TODO>` Conciliar borrado GDPR vs. inmutabilidad: definir qué se anonimiza y qué se conserva del
  registro de auditoría tras el borrado del dato.
- `<TODO>` Índices JSONB/GIN para los atributos dinámicos de mayor uso en matching.
- `<TODO>` ¿Sello de tiempo externo (RFC 3161) o anclaje periódico del último hash para reforzar la
  cadena frente a un operador comprometido?

## Disparadores de revisión

- Los atributos dinámicos más usados se estabilizan → promover a columnas tipadas.
- Requisito legal de ledger verificable por terceros → evaluar anclaje externo / notarización.
- El volumen de auditoría degrada el rendimiento → particionar/archivar manteniendo la cadena.
