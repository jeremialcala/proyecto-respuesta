# chatbot-gateway

Canal principal de Respuesta (ADR-0001 LLM on-prem + ADR-0002 NeMo Guardrails). Consume
`inbound.text` (del [meta-handler](../meta-handler)), aplica **rieles de entrada**, conversa con el
**LLM on-premises** (Ollama, **no autoritativo**), aplica **rieles de salida** y publica
`outbound.reply` y —si extrae un reporte completo— `report.received`.

## Garantías (cubiertas por tests)

- **LLM no autoritativo**: el servicio **nunca** emite `state.changed` ni eventos de match; solo
  conversa y **captura** un borrador de reporte (lo confirma el core-backend).
- **Riel de entrada**: prompt-injection/jailbreak/exfiltración → **bloqueado** con respuesta segura,
  **sin invocar al LLM**. Insultos → se marca y se responde con **tono cordial**, sin bloquear.
- **Riel de salida**: si la respuesta del LLM intenta filtrar datos o ejecutar acciones → respuesta
  de respaldo segura (no se entrega la salida del modelo).
- La ubicación se reconoce como **contexto** (ack cordial), sin LLM.

## Arquitectura (Clean Architecture / DDD)

```
src/chatbot_gateway/
├── domain/        # puro: guardrails (input/output), models
├── application/   # ports (BodyCipher, LlmClient, ReplyPublisher, ReportPublisher, EventLog) + chatbot_service + events
├── adapters/      # ollama_llm, sqs_consumer, sqs_publisher, passthrough_cipher, noop_event_log
└── config.py
```

## MVP / pendiente fase 03

- El **LLM** corre en un servicio aparte (Ollama on GPU; ADR-0001/0006, RTX 3090). Este servicio solo
  orquesta y es CPU-ligero.
- Rieles: heurística pura (primera línea barata). Los **rieles NeMo con modelo guardián** (self-check)
  se añaden como port en fase 03.
- `BodyCipher` es passthrough (reverso del placeholder del meta-handler) → **Vault JWE** real en fase 03.
- Guarda de **opt-in/relay** entre actores y store Event/EventAction: fase 03.

## Estado

- ✅ Guardarraíles + `ChatbotService` con **12 tests en verde** (fakes; sin LLM real).
- 🚧 Adaptador Ollama y SQS con deps perezosas; rieles NeMo y JWE/Vault en fase 03.

## Ejecutar

```bash
pip install -e ".[test]" && pytest
pip install -e . && python -m chatbot_gateway
```
