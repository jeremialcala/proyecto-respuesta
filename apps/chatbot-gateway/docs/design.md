# Diseño — chatbot-gateway

- **Fase AI-DLC:** 03-implementation (test-first)
- **Decisión base:** [ADR-0001](../../../docs/00-project/adr/0001-llm-on-premises.md) (LLM on-prem) ·
  [ADR-0002](../../../docs/00-project/adr/0002-nemo-guardrails-prompt-injection.md) (guardarraíles) ·
  [ADR-0012](../../../docs/00-project/adr/0012-broker-aws-sqs-sns.md) (SQS) ·
  [ADR-0015](../../../docs/00-project/adr/0015-memoria-conversacion-pgvector.md) (memoria de conversación) ·
  sobre [ADR-0011](../../../docs/00-project/adr/0011-contrato-eventos.md)
- **Vista C4:** [c4-component-chatbot](../../../docs/architecture/c4-component-chatbot.md)

## Flujo

1. Consume `inbound.text` desde SQS; descifra el cuerpo JWE.
2. **Identidad + contexto** (ADR-0015): `conversation_key = sha256(bot_id|channel|contact_ref)`
   identifica al interlocutor; `ConversationStore.load` trae el perfil de sesión acumulado, la
   ventana reciente de turnos y los turnos antiguos relevantes (recuperación semántica con `Embedder`).
3. **Riel de entrada** (`domain/guardrails.screen_input`): injection → bloquea (respuesta segura,
   sin LLM); abuso → marca (tono cordial).
4. **LLM on-prem** (`LlmClient.converse(user_text, context)`, Ollama): respuesta + borrador de
   reporte estructurado, usando el contexto de la conversación. No autoritativo.
5. **Riel de salida** (`screen_output`): fuga/acción → respuesta de respaldo; ok → entrega.
6. Publica `outbound.reply`. Persiste los turnos (usuario y asistente) y **acumula** el borrador
   sobre el `SessionProfile`. Si el reporte acumulado a lo largo de la conversación queda completo
   (intención + nombre + tipo + nº id) **y aún no se emitió** → publica `report.received` una sola
   vez (captura; lo confirma el core-backend).
7. Borra el mensaje de SQS sólo si terminó OK; si falla, redrive a DLQ (ADR-0012).

## Contexto de conversación (ADR-0015)

- **Estado por contacto:** `domain/conversation.py` — `conversation_key`, `Turn`, `SessionProfile`
  (perfil + borrador acumulado, `report_emitted`), `ConversationContext`.
- **Puertos:** `ConversationStore` (load/append_turn/save_profile) y `Embedder` (embed).
- **Adaptadores:** `PgConversationStore` (Postgres+pgvector, tablas `chat_sessions`/`chat_turns`,
  `embedding vector(768)`, recuperación con `<=>`) y `MemoryConversationStore` (dev/tests);
  `OllamaEmbedder` (`nomic-embed-text`) y `NullEmbedder`.
- **Economía del LLM:** prompt = resumen del perfil + ventana reciente (N) + top-k semántico (k), en
  vez de todo el historial. Configurable: `CHAT_RECENT_TURNS`, `CHAT_RETRIEVAL_K`, `EMBED_MODEL`, `EMBED_DIM`.
- **Degradación:** sin `PGVECTOR_DSN` → memoria; sin embeddings o si fallan → solo ventana reciente.

## Invariantes (cubiertos por tests)

- El servicio nunca emite `state.changed`/match (LLM no autoritativo).
- Injection no llega al LLM; la salida del LLM siempre pasa el riel antes de entregarse.
- Reporte incompleto no se publica como `report.received`.
- El reporte se completa **acumulando turnos** y se publica **una sola vez** (no se republica).
- Dos contactos distintos tienen contexto **aislado** (no comparten memoria).

## Pendiente (fase 03/04)

- Rieles NeMo Guardrails con modelo guardián (self-check, jailbreak) como port adicional.
- JWE real con Vault (reemplazar passthrough), guarda de opt-in/relay entre actores.
- Prompt/plantilla de extracción afinados.
- Job de retención (`purge_older_than`) y ventana exacta (ADR-0007); resolución a identidad
  verificada (ADR-0009) sobre el perfil; resumen rolling en conversaciones largas.
