# Diseño — vault-worker

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0005](../../../docs/00-project/adr/0005-webhook-manager-vault-worker.md) ·
  cifrado [ADR-0008](../../../docs/00-project/adr/0008-boveda-llaves-identidad.md) ·
  transporte [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) ·
  sobre [ADR-0011](../../../docs/00-project/adr/0011-contrato-eventos.md)
- **Vista C4:** [c4-component-webhook](../../../docs/architecture/c4-component-webhook.md)

## Flujo

1. Consume `inbound.media` desde SQS (`media_id`, `contact_ref`, `event_id`).
2. **Descarga** el binario de la Graph API por `media_id` (token del bot desde secrets).
3. **Escanea**: `(av_clean, csam_hit)` → veredicto `domain/scan.py` (**CSAM > MALWARE > CLEAN**).
4. **CSAM** → bloquea (no persiste, no publica, EventAction de alta severidad).
   **Malware** → cifra y va a **cuarentena** (sin publicar).
   **Limpio** → cifra de sobre (DEK por sujeto) → S3 bóveda → publica `media.stored` (scan=clean).
5. Borra el mensaje de SQS sólo si terminó OK; si falla, redrive a DLQ (ADR-0012).

## Pendiente (fase 03/04)

- ClamAV + lista de hashes CSAM reales (reemplazar `PassthroughScanner`).
- Vault Transit para la **clave por usuario** y rotación (ADR-0008).
- Cola/incidente CSAM y store Event/EventAction (ADR-0005).
- Soporte de audio/video (MVP: imagen).
