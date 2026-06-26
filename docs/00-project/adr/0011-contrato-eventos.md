# ADR-0011: Contrato común de eventos (sobre estándar + catálogo de eventos)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A04 (data), A08 (integridad de eventos), A09 (auditoría)
- **Relacionado:** RF-04/07/08/13, RS-06, [ADR-0005](0005-webhook-manager-vault-worker.md) (AMQP/JWE), [ADR-0004](0004-motor-de-matching.md), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md), [ADR-0010](0010-back-office-roles-flujos.md), `asyncapi.yaml`

## Contexto

Cuatro componentes (bot/ingestión, motor de matching, back office, notificador) ya intercambian
eventos por AMQP (ver `asyncapi.yaml` y ADR-0005), pero cada uno define su payload por separado. Sin
un **sobre común** no hay trazabilidad uniforme, versionado consistente, ni correlación fiable entre
etapas. Esta decisión fija el contrato compartido que **todos** los eventos adoptan.

## Decisión

**1. Sobre estándar (metadata base).** Todo evento del sistema adopta el mismo sobre; el `payload`
varía por `event_type`:

```json
{
  "event_id": "uuid-v4",
  "event_type": "dominio.evento",
  "producer": "componente-origen",
  "timestamp": "2026-06-26T16:20:00Z",
  "version": "1.0.0",
  "payload": {}
}
```

- `event_type` sigue la convención **`dominio.evento`** en minúsculas.
- `version` es **semver**; cambios incompatibles suben el major y conviven por transición.
- `event_id` es la clave de **idempotencia** y de correlación end-to-end.

**2. Transporte: AMQP** (broker del ADR-0005, con DLX/DLQ por canal). Los cuerpos con PII o
biométricos viajan **cifrados en JWE** (patrón del ADR-0005); el sobre (metadata) va en claro para
enrutamiento y auditoría.

**3. Catálogo canónico de eventos del flujo central** (consolidando `asyncapi.yaml`):

| `event_type` | Productor → Consumidor | Reemplaza/mapea | Payload (resumen) |
| :---- | :---- | :---- | :---- |
| `reporte.creado` | core-backend → matching | (≈ `report.received`/`report.ingested`) | `reporte_id`, `tipo_fuente`, `rostro` (ref a embedding en pgvector + calidad), `contexto_fusion` (geo, texto), `metadata_sujeto` |
| `match.evaluado` | worker-matching → back office/notificador | (≈ `candidate.generated`) | `reporte_id`, `match_encontrado`, `score_fusion_final`, `criterio_decision` (umbral, distancia coseno, pesos efectivos), `candidato_desaparecido`, `band`, `routing` |
| `match.resuelto` | back office → notificador/auditoría | **nuevo** (ADR-0010) | `match_id`, `decision` (`MATCHED`/`DISCARDED`), `coordinador` (usuario+ID), `justificacion`, firma |
| `notificacion.estado_cambiado` | notificator-service → canales/auditoría | (≈ `state.changed`/`notification.sent`) | `reporte_id`, `desaparecido_id`, `estado_anterior`, `estado_nuevo`, `nivel_alerta`, `canales_notificados[]` |

Ejemplos completos de `reporte.creado`, `match.evaluado` y `notificacion.estado_cambiado` en el
inventario (`inventario-definiciones-mvp.md`, sección 9) y reflejados en `asyncapi.yaml`.

**4. Regla de biométricos en el bus.** El embedding facial **no viaja inline** en `reporte.creado`:
se referencia su ubicación en **pgvector** (ADR-0004/0007), o si debe viajar, va en el **cuerpo JWE**.
El sobre nunca lleva PII ni biométrico en claro (alinea ADR-0005: medios y biométricos no fluyen
libres por la red/eventos).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Sobre común + catálogo versionado sobre AMQP** ✅ | Trazabilidad e idempotencia uniformes; versionado semver; correlación por `event_id`; reúne lo disperso en `asyncapi.yaml` | Hay que migrar los nombres actuales al catálogo; disciplina de versionado | Sobre en claro para auditoría; cuerpos sensibles en JWE (A04) |
| **B. Cada componente con su payload (status quo)** | Sin trabajo de unificación | Sin trazabilidad ni versionado consistentes; correlación frágil | Difícil auditar integridad de la cadena (A08/A09) |
| **C. Embedding inline en los eventos** | Un solo mensaje autocontenido | Biométrico (Restringido) circulando por el bus; mensajes pesados | Exposición de biométricos en el transporte (A04) — descartada |

## Consecuencias

- **Positivas:** un único sobre da **trazabilidad, idempotencia y versionado** homogéneos a los
  cuatro componentes; el catálogo canónico elimina la ambigüedad de payloads; la correlación por
  `event_id` enlaza reporte→match→resolución→notificación de punta a punta (alimenta la auditoría
  SHA-256 del ADR-0007); el nuevo `match.resuelto` cierra el ciclo del match manual del ADR-0010.
- **Negativas / deuda asumida:** hay que **migrar** los nombres de `asyncapi.yaml`
  (`report.received`, `candidate.generated`, `state.changed`, …) al catálogo `dominio.evento` y
  mantener una **tabla de equivalencias** durante la transición; el versionado semver exige
  disciplina (eventos conviviendo en major distintos); separar sobre (claro) de cuerpo (JWE) añade
  complejidad de serialización.
- **Impacto en threat model:**
  - **A08 (integridad de eventos):** `event_id` + versionado + auditoría encadenada detectan pérdida
    o manipulación; DLQ del ADR-0005 evita descartes silenciosos.
  - **A04 (biométricos):** embeddings por referencia/JWE, nunca en claro en el sobre.
  - **A09:** el sobre estándar es la base del registro de auditoría correlacionable.

## Decisiones abiertas

- `<TODO>` **Convención de nombres definitiva**: el inventario usa `reporte.creado`/`match.evaluado`/
  `notificacion.estado_cambiado` (ES) y `asyncapi.yaml` usa `report.received`/`candidate.generated`/
  `state.changed` (EN). Elegir una y migrar la otra (recomendado: una sola convención en todo el
  catálogo).
- `<TODO>` **Broker**: el inventario menciona **SQS** para la cola de ingestión, pero ADR-0005,
  `asyncapi.yaml`, el C4 y el código (`amqp_consumer.py`) están sobre **AMQP/RabbitMQ** con DLX/DLQ.
  Reconciliar (recomendado: mantener AMQP por la dependencia del diseño event-driven; SQS exigiría
  rehacer DLX, JWE-routing y el patrón cola+worker).
- `<TODO>` Registro de esquemas (schema registry) y linting de los eventos en CI.
- `<TODO>` Estrategia de migración/coexistencia de versiones (major) sin romper consumidores.

## Disparadores de revisión

- Aparece un quinto componente productor/consumidor → validar que el sobre lo cubre.
- Un evento necesita cambio incompatible → bump de major y plan de coexistencia.
- Se decide cambiar de broker → reevaluar JWE-routing, DLX y el patrón cola+worker.
