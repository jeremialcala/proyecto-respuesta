# Diseño — meta-handler

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0005](../../../docs/00-project/adr/0005-webhook-manager-vault-worker.md) ·
  [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) ·
  sobre [ADR-0011](../../../docs/00-project/adr/0011-contrato-eventos.md)
- **Vista C4:** [c4-component-webhook](../../../docs/architecture/c4-component-webhook.md)

## Flujo

1. Consume el sobre `meta.received` (publicado por el webhook-gateway) desde SQS.
2. **Normaliza** (`domain/normalize.py`): `object` → canal; extrae `contact_ref` (`from`),
   `message_id` y el tipo (text/image/location/unsupported) con su contenido. Las **respuestas
   interactivas** de WhatsApp (`type:"interactive"` → `button_reply`/`list_reply`, p. ej. al desambiguar
   rostros, ADR-0016) se **aplanan a TEXT** con el título de la opción tocada, para que el chatbot las
   resuelva como un texto normal (`parse_selection`).
3. **Reparte** (`application/handler_service.py`):
   - text/location → `inbound.text` (cuerpo JWE; el `contact_ref` va en claro como referencia).
   - image → `inbound.media` (solo `media_id` + `mime`; el binario lo baja la Bóveda).
   - unsupported / canal ≠ WhatsApp → `EventAction` SKIP y descarte.
4. Borra el mensaje de SQS sólo si el reparto fue OK; si falla, redrive a DLQ (ADR-0012).

## Invariantes (cubiertos por tests)

- El binario **nunca** viaja en `inbound.media` (solo `media_id`).
- El cuerpo de `inbound.text` va **cifrado** (port `BodyCipher`); `contact_ref` separado.
- Lote mixto: cuenta correcta de text/media/skipped; un tipo no soportado no rompe el resto.

## Pendiente (fase 03/04)

- Cifrador **JWE real con Vault Transit** (reemplazar `PassthroughCipher`) — ADR-0008.
- **Event/EventAction store** en Postgres (traza por pasos) — ADR-0005.
- Resolución de contacto enriquecida (perfil/`contacts[]`) y soporte multi-canal (page/instagram).
