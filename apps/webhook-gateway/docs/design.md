# Diseño — webhook-gateway

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0005](../../../docs/00-project/adr/0005-webhook-manager-vault-worker.md)
  (ingestión Meta) · [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) (SQS/SNS) ·
  sobre de eventos [ADR-0011](../../../docs/00-project/adr/0011-contrato-eventos.md)
- **Vista C4:** [c4-component-webhook](../../../docs/architecture/c4-component-webhook.md)

## Flujo

**GET** `/webhooks/{network}/{bot_id}` → si `hub.mode=subscribe` y `hub.verify_token` coincide con el
bot, responde `hub.challenge` (200); si no, 403.

**POST** `/webhooks/{network}/{bot_id}`:
1. Lee el **cuerpo crudo** (bytes) y el header `X-Hub-Signature-256`.
2. **Firma** HMAC-SHA256 del cuerpo con el app secret → inválida ⇒ **403** (Meta no debe reintentar
   a un atacante).
3. **Parse mínimo** (`object` + message ids). `object` no soportado ⇒ ACK 200 sin publicar.
4. **Idempotencia**: `SET NX EX` en Redis por `{bot_id}:{message_id}`. Duplicado ⇒ ACK 200 sin
   publicar.
5. **Publica** el sobre `meta.received` (`event_id`, `producer=webhook-gateway`, `payload={bot_id,
   object, raw}`) a SQS y responde **200**.

## Invariantes (cubiertos por tests)

- El Gateway **no procesa**: su única salida es publicar el crudo (no resuelve contacto ni tipo).
- Firma inválida o bot desconocido → 403 y **nada publicado**.
- Duplicado y `object` no soportado → 200 y **nada publicado** (sin reintentos de Meta).
- ACK rápido: la publicación es la única operación de I/O en el camino feliz.

## Pendiente (fase 03/04)

- Catálogo de bots (verify_token/app_secret) en Postgres/Vault en vez de entorno (ADR-0005/0008).
- TTL de idempotencia y métricas (edad de cola, ratio de duplicados) — afinar.
- Pruebas de integración con Redis + SQS reales y un túnel de Meta; rate-limit en el edge/WAF.
- Siguientes servicios de la cadena: **Meta Handler** (consume `meta.received`) y **Worker de Bóveda**.
