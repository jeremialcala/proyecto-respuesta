# ADR-0011: Contrato común de eventos (sobre estándar + catálogo de eventos)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A04 (data), A08 (integridad de eventos), A09 (auditoría)
- **Relacionado:** RF-04/07/08/13, RS-06, [ADR-0005](0005-webhook-manager-vault-worker.md), [ADR-0012](0012-broker-aws-sqs-sns.md) (transporte SQS/SNS + JWE), [ADR-0004](0004-motor-de-matching.md), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md), [ADR-0010](0010-back-office-roles-flujos.md), `asyncapi.yaml`

## Contexto

Cuatro componentes (bot/ingestión, motor de matching, back office, notificador) ya intercambian
eventos por el broker (ver `asyncapi.yaml` y ADR-0005), pero cada uno define su payload por separado. Sin
un **sobre común** no hay trazabilidad uniforme, versionado consistente, ni correlación fiable entre
etapas. Esta decisión fija el contrato compartido que **todos** los eventos adoptan.

## Decisión

**1. Sobre estándar (metadata base).** Todo evento del sistema adopta el mismo sobre; el `payload`
varía por `event_type`:

```json
{
  "event_id": "uuid-v4",
  "event_type": "domain.event",
  "producer": "componente-origen",
  "timestamp": "2026-06-26T16:20:00Z",
  "version": "1.0.0",
  "payload": {}
}
```

- `event_type` sigue la convención **`domain.event`** en **inglés**, minúsculas (estándar del código).
- `version` es **semver**; cambios incompatibles suben el major y conviven por transición.
- `event_id` es la clave de **idempotencia** y de correlación end-to-end.

**2. Transporte: AWS SQS/SNS** ([ADR-0012](0012-broker-aws-sqs-sns.md)): colas SQS para el patrón
cola+worker, topics SNS para fan-out, DLQ nativa por redrive. Los cuerpos con PII o biométricos
viajan **cifrados en JWE** (no se delega la confidencialidad al broker; SSE-KMS adicional); el sobre
(metadata) va en claro para enrutamiento y auditoría. Entrega *at-least-once* → idempotencia por
`event_id` obligatoria.

**3. Catálogo canónico de eventos del flujo central** (nombres en **inglés**, consolidando
`asyncapi.yaml`):

| `event_type` | Productor → Consumidor | Payload (resumen) |
| :---- | :---- | :---- |
| `report.received` | core-backend → cola | Reporte capturado y encolado (offline-first) |
| `report.ingested` | worker → matching | Adjuntos en almacén protegido; `report_id`, `entity_id`, `media_ref`, `face` (ref a embedding 512-d en pgvector + calidad) |
| `candidate.generated` | worker-matching → back office/notificador | `report_id`, `match_found`, `face_score`, `decision_criteria` (umbral, distancia coseno), `missing_candidate`, `band`, `routing` |
| `match.confirmed` | coordinador/sistema → notificación | Match confirmado (coordinador ≥65 % o autoreporte 100 %) |
| `match.resolved` | back office → notificación/auditoría | **nuevo** (ADR-0010): `match_id`, `decision` (`MATCHED`/`DISCARDED`), `coordinator` (usuario+ID), `justification`, `signature` |
| `state.changed` | API → notificación + auditoría | Transición de estado (auditada) |
| `notification.sent` | notificación → canal | `entity_id`, `from_state`, `to_state`, `alert_level`, `channels_notified[]` |

> Los nombres en español del inventario (`reporte.creado`, `match.evaluado`,
> `notificacion.estado_cambiado`) son **ilustrativos**; el catálogo canónico es el inglés de arriba.
> Ejemplos de payload en el inventario (`inventario-definiciones-mvp.md`, sección 9), a migrar a EN.

**4. Regla de biométricos en el bus.** El embedding facial (512-d, ArcFace — ADR-0013) **no viaja inline** en `report.ingested`:
se referencia su ubicación en **pgvector** (ADR-0004/0007), o si debe viajar, va en el **cuerpo JWE**.
El sobre nunca lleva PII ni biométrico en claro (alinea ADR-0005: medios y biométricos no fluyen
libres por la red/eventos).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Sobre común + catálogo versionado sobre el broker (SQS/SNS)** ✅ | Trazabilidad e idempotencia uniformes; versionado semver; correlación por `event_id`; reúne lo disperso en `asyncapi.yaml` | Hay que migrar los nombres actuales al catálogo; disciplina de versionado | Sobre en claro para auditoría; cuerpos sensibles en JWE (A04) |
| **B. Cada componente con su payload (status quo)** | Sin trabajo de unificación | Sin trazabilidad ni versionado consistentes; correlación frágil | Difícil auditar integridad de la cadena (A08/A09) |
| **C. Embedding inline en los eventos** | Un solo mensaje autocontenido | Biométrico (Restringido) circulando por el bus; mensajes pesados | Exposición de biométricos en el transporte (A04) — descartada |

## Consecuencias

- **Positivas:** un único sobre da **trazabilidad, idempotencia y versionado** homogéneos a los
  cuatro componentes; el catálogo canónico elimina la ambigüedad de payloads; la correlación por
  `event_id` enlaza reporte→match→resolución→notificación de punta a punta (alimenta la auditoría
  SHA-256 del ADR-0007); el nuevo `match.resolved` cierra el ciclo del match manual del ADR-0010.
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

- ✅ **Resuelto — Convención de nombres**: **inglés** (`domain.event`) como estándar del código; los
  nombres en español quedan como ilustrativos y se migran.
- ✅ **Resuelto — Broker**: **AWS SQS/SNS** ([ADR-0012](0012-broker-aws-sqs-sns.md)); reemplaza AMQP.
- `<TODO>` Registro de esquemas (schema registry) y linting de los eventos en CI.
- `<TODO>` Estrategia de migración/coexistencia de versiones (major) sin romper consumidores.

## Disparadores de revisión

- Aparece un quinto componente productor/consumidor → validar que el sobre lo cubre.
- Un evento necesita cambio incompatible → bump de major y plan de coexistencia.
- Se decide cambiar de broker → reevaluar JWE-routing, DLX y el patrón cola+worker.
