# Diseño — chatbot-gateway

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0001](../../../docs/00-project/adr/0001-llm-on-premises.md) (LLM on-prem) ·
  [ADR-0002](../../../docs/00-project/adr/0002-nemo-guardrails-prompt-injection.md) (guardarraíles) ·
  [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) (SQS) ·
  sobre [ADR-0011](../../../docs/00-project/adr/0011-contrato-eventos.md)
- **Vista C4:** [c4-component-chatbot](../../../docs/architecture/c4-component-chatbot.md)

## Flujo

1. Consume `inbound.text` desde SQS; descifra el cuerpo JWE.
2. **Riel de entrada** (`domain/guardrails.screen_input`): injection → bloquea (respuesta segura,
   sin LLM); abuso → marca (tono cordial).
3. **LLM on-prem** (`LlmClient.converse`, Ollama): respuesta + borrador de reporte estructurado. No
   autoritativo.
4. **Riel de salida** (`screen_output`): fuga/acción → respuesta de respaldo; ok → entrega.
5. Publica `outbound.reply`; si el borrador tiene núcleo obligatorio (nombre+tipo+nº id) → publica
   `report.received` (captura; lo confirma el core-backend).
6. Borra el mensaje de SQS sólo si terminó OK; si falla, redrive a DLQ (ADR-0012).

## Invariantes (cubiertos por tests)

- El servicio nunca emite `state.changed`/match (LLM no autoritativo).
- Injection no llega al LLM; la salida del LLM siempre pasa el riel antes de entregarse.
- Reporte incompleto no se publica como `report.received`.

## Pendiente (fase 03/04)

- Rieles NeMo Guardrails con modelo guardián (self-check, jailbreak) como port adicional.
- JWE real con Vault (reemplazar passthrough), guarda de opt-in/relay entre actores.
- Prompt/España de extracción afinados; manejo de conversación multi-turno (estado por contacto).
