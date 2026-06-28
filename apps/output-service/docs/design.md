# Diseño — output-service

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0005](../../../docs/00-project/adr/0005-webhook-manager-vault-worker.md)
  (servicio de salida) · [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) (SQS) ·
  ventana de 24h / plantilla HSM (charter, componente 1) ·
  [ADR-0016](../../../docs/00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md) (desambiguación) ·
  [ADR-0017](../../../docs/00-project/adr/0017-media-delivery-gateway.md) (URL firmada de medios)
- **Vista C4:** [c4-component-webhook](../../../docs/architecture/c4-component-webhook.md) (servicio de salida)

## Flujo

1. Consume `outbound.reply` desde SQS; descifra el cuerpo.
2. Consulta la **ventana de 24h** del contacto (Redis).
3. **Si el reply trae `media_refs`** (desambiguación multi-rostro, ADR-0016) y la ventana está abierta →
   **rama de selección de rostro**: por cada `crop_ref` pide una concesión al **media-gateway**
   (`POST /grants`, `purpose=disambiguation_crop`, etiquetada con `report_id`) y envía una **imagen** a
   Meta con la URL firmada (`send_image`), luego un **botón de opciones** (`send_buttons` si ≤2 rostros,
   `send_list` si ≥3) — labels `"Rostro N"`/`"Ninguno"`, parseables por el chatbot.
4. Si no hay `media_refs`: `domain/delivery.choose_delivery` → abierta → texto; cerrada → plantilla HSM.
5. Envía por la Graph API (WhatsApp Cloud API `/{phone_number_id}/messages`).
6. Borra el mensaje de SQS sólo si el envío fue OK; si falla, redrive a DLQ (ADR-0012).

## Puertos

`MetaSender` (`send_text`/`send_template`/`send_image`/`send_buttons`/`send_list`), `BodyCipher`,
`WindowStore`, `MediaGrantClient` (emite concesiones en el media-gateway) y `EventLog`.

## Pendiente (fase 03/04)

- JWE real con Vault (reemplazar passthrough).
- Catálogo de plantillas HSM y mapeo de errores de la Graph API (reintento vs DLQ).
- Métricas (entregas, ratio plantilla vs texto, imágenes servidas) y traza Event/EventAction.
