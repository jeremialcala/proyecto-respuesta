# webhook-gateway

Borde de ingestión de Meta para Respuesta. Implementa el **Webhook Gateway** de
[ADR-0005](../../docs/00-project/adr/0005-webhook-manager-vault-worker.md) sobre **AWS SQS/SNS**
([ADR-0012](../../docs/00-project/adr/0012-broker-aws-sqs-sns.md)): único endpoint público que Meta
golpea. **Convención clave:** no procesa ni toca workers — solo **verifica, deduplica y publica el
payload crudo** a `meta.received`.

## Responsabilidades (y lo que NO hace)

- ✅ Handshake `GET` de verificación (`hub.challenge` si `hub.verify_token` coincide, por bot).
- ✅ Validación de firma **`X-Hub-Signature-256`** (HMAC del app secret) — cierra T1/T11.
- ✅ **Idempotencia** por `message_id` (`wamid.…`) en Redis (Meta reintrega) — ACK 200 al duplicado.
- ✅ **ACK <5s** y publicación del crudo a `meta.received` (sobre estándar ADR-0011).
- ❌ No normaliza el contacto, no identifica tipos, no baja binarios, no llama al LLM ni al almacén
  (eso es del **Meta Handler** y el **Worker de Bóveda**, fases siguientes).

## Arquitectura (Clean Architecture / DDD)

```
src/webhook_gateway/
├── domain/        # puro: signature (HMAC), meta_payload (object + message ids)
├── application/   # ports (IdempotencyStore, RawPublisher) + ingest_service + events (sobre)
├── adapters/      # redis_idempotency, sqs_raw_publisher (deps perezosas)
├── api/           # app.py (FastAPI: GET verify / POST receive)
└── config.py      # GatewayConfig/BotConfig desde entorno
```

Regla de dependencia: hacia adentro. El dominio y la aplicación no conocen FastAPI/boto3/redis.

## MVP

WhatsApp Business (`object = whatsapp_business_account`). Otros `object` se ACK-ean pero no se
publican hasta habilitarlos. Bot único por entorno; en producción el catálogo de bots
(verify_token/app_secret) vive en Postgres/Vault (ADR-0005/0008).

## Estado

- ✅ Dominio (firma, payload) y `IngestService` con **15 tests en verde** (fakes; sin infra).
- 🚧 Adaptadores Redis/SQS y API FastAPI implementados con deps perezosas; prueba con infra real
  (Redis, SQS, túnel de Meta) en fase 03.

## Ejecutar

```bash
pip install -e ".[test]" && pytest          # tests del dominio/servicio (sin infra)
# runtime:
pip install -e .
uvicorn webhook_gateway.__main__:app --port 8080
```

Variables: `META_BOT_ID`, `META_VERIFY_TOKEN`, `META_APP_SECRET`, `SQS_RAW_QUEUE_URL`,
`REDIS_URL`, `AWS_REGION` (default `sa-east-1`).
