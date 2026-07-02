# C4 — Diagrama de Componentes: Evaluador de respuestas del chatbot · Respuesta

> **C4 — Component view · AI-DLC Fase 02 (Design)**
>
> Pipeline escalonado de calidad conversacional ([ADR-0022](../00-project/adr/0022-evaluador-respuestas-chatbot.md)):
> toda respuesta generada por el LLM pasa, tras los output rails de NeMo
> ([ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md)), por tres etapas —
> chequeos deterministas, redundancia semántica sobre pgvector
> ([ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)) y juez LLM condicional —
> antes de publicarse en `outbound.reply`. Veredicto negativo → regeneración con feedback (máx. 2)
> → plantilla segura. En rojo las reglas duras: el evaluador **veta pero no edita ni mueve
> estados**, la redundancia **no cruza conversaciones** y los eventos de auditoría **no llevan
> texto ni PII**.

```mermaid
C4Component
    title Diagrama de componentes — Evaluador de respuestas (Pasarela de Chatbot)

    Container(llm, "LLM on-premises", "Ollama, modelo 7-14B", "Genera la respuesta candidata (ADR-0001)")
    Container(guardian, "Modelo guardián", "LLM pequeño compartido con NeMo", "Rúbrica de adecuación/relevancia (ADR-0002)")

    Container_Boundary(cb, "Pasarela de Chatbot") {
        Component(orchestrator, "Orquestador LLM", "LLM autenticado", "Conversa y regenera con el feedback del veredicto (máx. 2)")
        Component(guardrails, "Rieles de guardarraíles", "NeMo Guardrails", "Output rails de SEGURIDAD; corren antes del evaluador")
        Component(evaluator, "Evaluador de respuestas", "Coordinador del pipeline", "Veredicto {adequacy, relevance, redundancy}; modos enforce/shadow; pass-through auditado si falla")
        Component(stage1, "Etapa 1 — Chequeos deterministas", "CPU", "Formato, idioma, placeholders, re-pregunta de datos ya en SessionProfile")
        Component(stage2, "Etapa 2 — Redundancia semántica", "Embeddings + pgvector", "Coseno vs. turnos previos del asistente en la MISMA conversation_key (τ_rep)")
        Component(stage3, "Etapa 3 — Juez condicional", "Rúbrica JSON validada", "Adecuación y relevancia; conversación como DATOS delimitados")
        Component(fallback, "Plantillas seguras", "Determinista", "Fallback al agotar reintentos; exentas de evaluación")
        Component(outbound, "Servicio de salida", "outbound.reply", "Entrega por adaptadores de canal")
    }

    ContainerDb(convdb, "Memoria de conversación", "Postgres + pgvector", "Turnos, embeddings y SessionProfile (ADR-0015)")
    ContainerQueue(broker, "Broker de eventos", "AWS SQS/SNS", "response.evaluated — solo scores y referencias, sin PII (ADR-0011/0012)")

    Rel(orchestrator, llm, "Inferencia (on-prem)", "")
    Rel(orchestrator, guardrails, "Respuesta candidata", "")
    Rel(guardrails, evaluator, "Respuesta saneada (seguridad OK)", "")
    Rel(evaluator, stage1, "1º", "")
    Rel(evaluator, stage2, "2º si no decide", "")
    Rel(evaluator, stage3, "3º condicional", "")
    Rel(stage1, convdb, "Lee SessionProfile", "SQL")
    Rel(stage2, convdb, "Similitud coseno por conversation_key", "pgvector")
    Rel(stage3, guardian, "Inferencia de rúbrica", "")
    Rel(evaluator, orchestrator, "fail + reasons[] → regenerar (máx. 2)", "")
    Rel(evaluator, fallback, "Reintentos agotados", "")
    Rel(evaluator, outbound, "pass → publicar", "")
    Rel(fallback, outbound, "Plantilla segura", "")
    Rel(evaluator, broker, "response.evaluated (auditoría)", "JSON")

    UpdateElementStyle(evaluator, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(stage2, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(stage3, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Notas de seguridad

El evaluador es una capa de **calidad**, no de seguridad: corre **después** de los output rails de
NeMo y **no los reemplaza** (A06). No es autoritativo — veta y explica, pero no edita respuestas ni
mueve estados; el backstop arquitectónico "LLM no autoritativo" ([ADR-0001](../00-project/adr/0001-llm-on-premises.md))
se preserva. El **juez condicional** es superficie nueva de prompt injection indirecta (el texto
del usuario viaja citado en el contexto de evaluación): recibe la conversación como **datos
delimitados** con rúbrica fija y su salida se valida contra esquema JSON (A05, `ai-sec`). La
**redundancia semántica** consulta pgvector estrictamente filtrada por `conversation_key` — cruzar
conversaciones sería una fuga entre interlocutores (A01) y se cubre con test de aislamiento. Los
eventos `response.evaluated` llevan **solo scores, referencias y contadores**, nunca texto de la
conversación (A04). Veredictos, reintentos, fallbacks, pass-through por fallo del evaluador y
cambios de modo enforce↔shadow quedan **auditados** (A09); la tasa de fallback es alarma operativa
y el tope de 2 regeneraciones acota el consumo de la GPU compartida bajo pico
([ADR-0001](../00-project/adr/0001-llm-on-premises.md)/[ADR-0018](../00-project/adr/0018-desacople-gpu-llm-facematch.md)).
