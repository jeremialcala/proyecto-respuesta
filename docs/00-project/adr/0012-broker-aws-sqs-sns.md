# ADR-0012: Broker de mensajería = AWS SQS/SNS (supersede el transporte AMQP de ADR-0005/0011)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (acceso), A02 (misconfiguration), A08 (integridad de eventos), A09 (auditoría)
- **Relacionado:** [ADR-0005](0005-webhook-manager-vault-worker.md) (transporte enmendado), [ADR-0011](0011-contrato-eventos.md), [ADR-0006](0006-residencia-sao-paulo.md) (AWS `sa-east-1`), `asyncapi.yaml`, C4 de contenedores

## Contexto

El [ADR-0005](0005-webhook-manager-vault-worker.md) y el [ADR-0011](0011-contrato-eventos.md)
modelaron toda la mensajería sobre **AMQP/RabbitMQ** (colas con DLX→`*.dlq`, patrón cola+worker,
cuerpos JWE). Con la residencia en AWS `sa-east-1` ([ADR-0006](0006-residencia-sao-paulo.md)) y la
decisión de **delegar la operación en servicios gestionados de AWS**, mantener un RabbitMQ
autoadministrado añade carga operativa que el proyecto (masivo, sin funding) quiere evitar. Esta
decisión cambia el **transporte**, no el patrón event-driven ni el contrato de eventos (ADR-0011).

## Decisión

Adoptamos **AWS SQS + SNS** como broker gestionado para toda la mensajería asíncrona.

- **SQS (colas)** para el patrón cola+worker: cada worker consume de su cola; entrega *at-least-once*
  → la idempotencia por `event_id`/`message.id` (ADR-0005/0011) sigue siendo obligatoria.
- **SNS (topics)** para el **fan-out**: los eventos con varios consumidores (p. ej. `state.changed`
  → Notificación **y** Auditoría) se publican en un topic SNS con suscripciones SQS por consumidor.
- **DLQ nativa por redrive policy**: cada cola SQS define una `redrivePolicy` con `maxReceiveCount`
  hacia su `*-dlq`. Reemplaza el DLX/DLX-routing de RabbitMQ; el **Gestor de DLQ** (ADR-0005) consume
  las colas `*-dlq` igual que antes.
- **Orden y deduplicación**: usar **SQS FIFO** solo donde el orden importe (p. ej. transiciones de
  estado de una misma entidad, con `MessageGroupId = entity_id`); el resto en **SQS Standard** por
  throughput/costo.
- **Cifrado**: SSE-SQS/SNS con KMS para el sobre; los cuerpos con PII/biométrico siguen en **JWE**
  (no se delega la confidencialidad del contenido al broker — alinea ADR-0008).
- **FastAPI/workers**: el webhook publica el crudo a un topic/cola; el resto del flujo igual.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. AWS SQS + SNS (gestionado)** ✅ | Cero ops de broker (alinea AWS/ADR-0006); DLQ nativa por redrive; escala automática; FIFO donde haga falta; SSE-KMS | At-least-once (exige idempotencia); fan-out obliga a SNS (no es un bus AMQP); routing por topic menos expresivo que exchanges; lock-in AWS | Confidencialidad del contenido sigue en JWE (no en el broker); IAM por cola/topic a endurecer (A01/A02) |
| **B. RabbitMQ/AMQP autogestionado** (ADR-0005 original) | Routing por exchange muy expresivo; DLX; portable | Operar HA, parches, escalado → carga sin funding; otro servicio que endurecer | Más superficie propia que asegurar (A02) |
| **C. Amazon MQ (RabbitMQ gestionado)** | Mantiene AMQP con menos ops | Sigue siendo broker dedicado con costo fijo; menos "serverless" que SQS/SNS | Similar a B con menos parcheo |
| **D. Kafka/MSK** | Alto throughput, log durable, replay | Sobre-ingeniería para el arranque; costo/operación altos | Más superficie y complejidad |

> **B/C** quedan como reversión si el routing por exchange se vuelve necesario; **D** si aparece
> necesidad real de replay/event-sourcing a gran escala.

## Consecuencias

- **Positivas:** se elimina la operación del broker (gestionado por AWS); DLQ y reintentos nativos
  (redrive) simplifican el ADR-0005; escala elástica para los picos del desastre; SSE-KMS + JWE
  mantienen la confidencialidad; FIFO da orden donde importa.
- **Negativas / deuda asumida:** **at-least-once** obliga a idempotencia disciplinada (ya prevista);
  el **fan-out** ahora requiere SNS (un topic + suscripciones por evento multiconsumidor) → más
  recursos que declarar; el routing por topic es **menos expresivo** que los exchanges de RabbitMQ;
  **lock-in AWS**; hay que **reescribir el adaptador** `amqp_consumer.py` del `matching-worker` a un
  consumidor SQS y rehacer las **bindings** de `asyncapi.yaml`.
- **Impacto en threat model:**
  - **A08 (integridad de eventos):** idempotencia por `event_id` + redrive a DLQ evitan pérdida y
    duplicado silencioso (sustituye DLX).
  - **A01/A02:** políticas IAM mínimas por cola/topic; SSE-KMS; el broker no ve el contenido (JWE).
  - **A09:** la auditoría sigue alimentándose del sobre estándar (ADR-0011).

## Decisiones abiertas

- `<TODO>` Mapa concreto evento→(topic SNS / cola SQS / FIFO vs Standard) y `maxReceiveCount` por cola.
- `<TODO>` Bindings SQS/SNS en `asyncapi.yaml` (reemplazar el server AMQP).
- `<TODO>` Reescritura del adaptador del `matching-worker` (`amqp_consumer.py` → consumidor SQS).
- `<TODO>` Estrategia de orden: qué flujos exigen FIFO y su `MessageGroupId`.

## Disparadores de revisión

- El routing por topic resulta insuficiente → evaluar Amazon MQ (C) o EventBridge.
- Aparece necesidad de replay/event-sourcing → evaluar Kafka/MSK (D).
- El costo de SQS/SNS a escala supera al de un broker dedicado → reevaluar C.
