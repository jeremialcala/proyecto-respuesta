# Diseño — output-service

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0005](../../../docs/00-project/adr/0005-webhook-manager-vault-worker.md)
  (servicio de salida) · [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) (SQS) ·
  ventana de 24h / plantilla HSM (charter, componente 1)
- **Vista C4:** [c4-component-webhook](../../../docs/architecture/c4-component-webhook.md) (servicio de salida)

## Flujo

1. Consume `outbound.reply` desde SQS; descifra el cuerpo.
2. Consulta la **ventana de 24h** del contacto (Redis).
3. `domain/delivery.choose_delivery`: abierta → texto; cerrada → plantilla HSM aprobada.
4. Envía por la Graph API (WhatsApp Cloud API `/{phone_number_id}/messages`).
5. Borra el mensaje de SQS sólo si el envío fue OK; si falla, redrive a DLQ (ADR-0012).

## Pendiente (fase 03/04)

- JWE real con Vault (reemplazar passthrough).
- Catálogo de plantillas HSM y mapeo de errores de la Graph API (reintento vs DLQ).
- Métricas (entregas, ratio plantilla vs texto) y traza Event/EventAction.
