# meta-handler

Segundo eslabón de la ingestión de Meta (ADR-0005) sobre **AWS SQS** (ADR-0012). Consume el crudo que
publica el [webhook-gateway](../webhook-gateway) en `meta.received`, lo **normaliza** y lo **reparte**:

- **texto / ubicación** → `inbound.text` con el cuerpo **cifrado en JWE** (rumbo al LLM on-prem).
- **imagen** → `inbound.media` con `media_id` + `mime` (el **binario no viaja**; lo baja el Worker de
  Bóveda).
- tipos no soportados / canales fuera del MVP → se registran y se descartan (no rompen el lote).

## Arquitectura (Clean Architecture / DDD)

```
src/meta_handler/
├── domain/        # puro: models, normalize (object/contacto/tipo → NormalizedMessage)
├── application/   # ports (InboundPublisher, BodyCipher, EventLog) + handler_service + events
├── adapters/      # sqs_consumer, sqs_inbound_publisher, jwe_cipher (placeholder), noop_event_log
└── config.py
```

## MVP

WhatsApp; tipos **text / image / location**. El cifrado JWE es un **placeholder explícito**
(`PassthroughCipher`) hasta integrar Vault Transit (ADR-0008) — no usar en producción tal cual. La
traza Event/EventAction (ADR-0005) es no-op hasta el store en Postgres (fase 03).

## Estado

- ✅ Dominio (normalize) + `HandlerService` con **11 tests en verde** (fakes; sin infra).
- 🚧 Adaptadores SQS con deps perezosas; JWE/Vault y Event store reales en fase 03.

## Ejecutar

```bash
pip install -e ".[test]" && pytest
pip install -e . && python -m meta_handler
```

Variables: `SQS_INPUT_QUEUE_URL` (meta-received), `SQS_TEXT_QUEUE_URL`, `SQS_MEDIA_QUEUE_URL`,
`AWS_REGION` (default `sa-east-1`).
