# output-service

Servicio de salida de Respuesta (ADR-0005). Consume `outbound.reply` (del
[chatbot-gateway](../chatbot-gateway) y, más adelante, del notificador) y **entrega la respuesta al
usuario por la Graph API** de Meta, eligiendo el modo según la **ventana de servicio de 24h**:

- **Dentro de la ventana** (hubo mensaje del usuario hace <24h) → **texto libre**.
- **Fuera de la ventana** → **plantilla HSM aprobada** (única del MVP, componente 1).

## Garantías (cubiertas por tests)

- La decisión texto-vs-plantilla es una **invariante de cumplimiento de Meta** (`domain/delivery.py`).
- Si Redis (estado de ventana) no responde → se asume **cerrada** → plantilla HSM (seguro: evita un
  texto rechazado por Meta).
- Idempotencia por `event_id` aguas arriba; fallo de envío → no se borra el mensaje (redrive a DLQ).

## Arquitectura (Clean Architecture / DDD)

```
src/output_service/
├── domain/        # puro: delivery (ventana→TEXT/TEMPLATE), models
├── application/   # ports (BodyCipher, WindowStore, MetaSender, EventLog) + output_service
├── adapters/      # graph_sender, redis_window_store, sqs_consumer, passthrough_cipher, noop_event_log
└── config.py
```

## MVP / pendiente fase 03

- La **marca de ventana** (TTL 24h por contacto en Redis) la pone la ingestión al recibir un mensaje
  del usuario; aquí solo se consulta.
- `BodyCipher` es passthrough (reverso del chatbot) → **Vault JWE** real en fase 03.
- Catálogo de plantillas HSM (hoy una sola) y manejo de errores específicos de la Graph API.

## Estado

- ✅ Decisión de entrega + `OutputService` con **5 tests en verde** (fakes; sin Graph real).
- 🚧 Adaptador Graph/Redis/SQS con deps perezosas.

## Ejecutar

```bash
pip install -e ".[test]" && pytest
pip install -e . && python -m output_service
```
