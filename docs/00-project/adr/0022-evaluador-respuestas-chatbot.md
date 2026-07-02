# ADR-0022: Evaluador de respuestas del chatbot — pipeline escalonado híbrido con regeneración con feedback

- **Estado:** accepted
- **Fecha:** 2026-07-02
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A05 (injection contra el juez), A06 (insecure design), A09 (logging/observabilidad), A01 (aislamiento entre conversaciones), A04 (PII en eventos), `ai-sec`
- **Relacionado:** [PRD evaluador](../../01-requirements/evaluador-respuestas-chatbot.md), [ADR-0001](0001-llm-on-premises.md) (LLM on-prem, GPU compartida), [ADR-0002](0002-nemo-guardrails-prompt-injection.md) (rieles NeMo), [ADR-0015](0015-memoria-conversacion-pgvector.md) (memoria pgvector), [ADR-0011](0011-contrato-eventos.md) (sobre de eventos), [ADR-0018](0018-desacople-gpu-llm-facematch.md) (presión sobre la GPU)

## Contexto

El [PRD del evaluador](../../01-requirements/evaluador-respuestas-chatbot.md) exige que toda
respuesta generada por el LLM sea evaluada en tres dimensiones — **adecuación** con lo solicitado,
**relevancia** de la información y **no-repetición** en el contexto de la conversación — antes de
publicarse en `outbound.reply`, con **regeneración con feedback** (máx. 2) y fallback a plantilla.

Fuerzas en juego:

- **Una sola GPU compartida** entre LLM, ArcFace y modelo guardián ([ADR-0001](0001-llm-on-premises.md)):
  cada inferencia extra por turno compite con el matching bajo el pico del desastre.
- **Ya existe infraestructura reutilizable:** embeddings por turno + pgvector
  ([ADR-0015](0015-memoria-conversacion-pgvector.md)) y el punto de corte de output rails de NeMo
  ([ADR-0002](0002-nemo-guardrails-prompt-injection.md)).
- La evaluación de **adecuación/relevancia** es semántica y contextual → algo de inferencia LLM es
  inevitable; la **repetición** en cambio es mayormente geométrica (similitud de embeddings) y
  determinista (dato ya presente en `SessionProfile`).
- El enforcement elegido (regenerar con feedback) exige que el evaluador sea **inline y
  bloqueante**, lo que pone la latencia y el costo en el camino crítico del turno.

## Decisión

Adoptamos un **evaluador escalonado híbrido, inline dentro de la Pasarela de Chatbot**, como etapa
posterior a los output rails de NeMo y previa a la publicación en `outbound.reply`:

**Etapa 1 — Chequeos deterministas (CPU, ~0 costo).** Formato, longitud, idioma, placeholders sin
resolver, y **re-pregunta de datos ya presentes** en el `SessionProfile` (repetición estructural).
Fallo aquí ni siquiera consulta modelos.

**Etapa 2 — Redundancia semántica (CPU + pgvector, barato).** El embedding de la respuesta
candidata (mismo `nomic-embed-text` de [ADR-0015](0015-memoria-conversacion-pgvector.md)) se
compara por coseno contra los embeddings de los **turnos previos del asistente** de la misma
`conversation_key`. Similitud ≥ τ_rep (inicial 0.90, calibrado en shadow) → repetida, salvo
excepción "el usuario pidió repetir". Complemento léxico (overlap de n-gramas) para casi-verbatim.

**Etapa 3 — Juez LLM condicional (GPU, acotado).** Un **modelo guardián pequeño** (el mismo
previsto para NeMo en [ADR-0002](0002-nemo-guardrails-prompt-injection.md), evitando cargar un
modelo más en VRAM) evalúa **adecuación** y **relevancia** con rúbrica y salida JSON validada por
esquema. Se invoca **condicionalmente**: cuando las etapas 1-2 no deciden y el turno lo amerita
(pregunta explícita del usuario, turnos largos, intención de alto valor). La conversación se le
pasa **como datos delimitados**, nunca como instrucciones (A05).

**Lazo de regeneración.** Veredicto `fail` → el orquestador regenera incluyendo `reasons[]` como
instrucción correctiva; **máximo 2 reintentos**; luego **plantilla segura** de fallback
(`fallback=true`). El evaluador **no es autoritativo**: no mueve estados ni edita la respuesta,
solo veta y explica (coherente con [ADR-0001](0001-llm-on-premises.md)).

**Observabilidad y modos.** Cada evaluación emite `response.evaluated` (sobre común
[ADR-0011](0011-contrato-eventos.md), sin texto ni PII). Flag de modo `enforce|shadow`; bajo
presión de GPU (profundidad de cola sobre umbral) el sistema **degrada automáticamente a shadow**
antes que perder turnos. Si el evaluador falla, pass-through auditado (`evaluator_skipped=true`).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
|---|---|---|---|
| **A. Pipeline escalonado híbrido inline (deterministas → embeddings → juez condicional) + regeneración** ✅ | Reutiliza embeddings/pgvector (ADR-0015) y el modelo guardián (ADR-0002) → costo marginal bajo; lo barato filtra primero y el juez solo corre cuando aporta; enforcement real (regenera antes de publicar); veredicto explicable por dimensión | Latencia añadida en el camino crítico; tres etapas que calibrar y mantener; el juez condicional exige una política de "cuándo invocar" | Juez expuesto a injection indirecta → datos delimitados + JSON por esquema (A05); eventos sin PII (A04); aislamiento por `conversation_key` (A01) |
| **B. Extender los output rails de NeMo (self-check en Colang)** | Una sola capa de salida; sin componente nuevo; rieles auditables | Colang está pensado para seguridad/rol, no para rúbricas de calidad multi-dimensión ni comparación vectorial contra pgvector; acopla calidad a la config de seguridad; regeneración con feedback rica es incómoda en rieles | Mezclar calidad y seguridad en la misma capa dificulta auditar cada una (A06) |
| **C. LLM-as-judge incondicional (segunda inferencia grande siempre)** | Máxima calidad de veredicto; implementación simple | **Duplica la carga de la GPU única por turno** bajo pico (inviable con ADR-0001/0018); latencia constante alta; costo no escala | La presión de GPU degrada también al matching → riesgo operativo del servicio completo |
| **D. Evaluador asíncrono consumiendo `outbound.reply` (servicio aparte, shadow permanente)** | Cero latencia añadida; desacoplado; escala aparte | **No bloquea nada**: la respuesta mala ya salió; contradice el enforcement elegido (regenerar); duplica acceso a la memoria conversacional desde otro servicio | Otro consumidor con acceso a contexto conversacional → superficie A01/A04 extra |
| **E. Clasificador entrenado propio (encoder fino sobre corpus etiquetado)** | Barato y rápido en inferencia; determinista | **No existe corpus etiquetado aún**; ciclo de entrenamiento/mantenimiento que un equipo sin funding no sostiene hoy | Drift silencioso del clasificador sin pipeline de reentrenamiento (A09) |

> D no se descarta: es exactamente el **modo shadow** de la opción A (mismo evaluador, flag
> distinto), y E es la **evolución post-MVP** natural cuando `response.evaluated` haya acumulado
> corpus para entrenar.

## Consecuencias

- **Positivas:** las tres dimensiones del requerimiento quedan cubiertas con costo marginal mínimo
  (repetición casi gratis vía pgvector ya existente; juez solo condicional); el usuario deja de
  recibir re-preguntas de datos ya entregados; el lazo de feedback mejora el prompt del orquestador
  con evidencia (`reasons[]` agregadas); shadow mode da calibración sin riesgo; la conversación
  nunca se bloquea (fallback + pass-through auditado).
- **Negativas / deuda asumida:** latencia añadida en el camino crítico (presupuestada en
  RNF-EV-01); tres umbrales/políticas que calibrar (τ_rep, política de invocación del juez, umbral
  de degradación a shadow); en el peor caso un turno cuesta hasta 3 inferencias (2 regeneraciones +
  juez) — el tope duro y la degradación automática acotan el daño; la calidad del juez está
  limitada por el modelo guardián pequeño (falsos negativos aceptados; E como evolución).
- **Impacto en threat model:**
  - **A05/`ai-sec`:** nueva superficie — injection indirecta contra el juez vía texto citado del
    usuario. Mitigación: datos delimitados, rúbrica fija, salida JSON validada por esquema, rieles
    de input ya corrieron antes.
  - **A01:** la comparación de redundancia debe quedar confinada a la `conversation_key`; una fuga
    cruzada expondría contenido entre conversaciones. Test de aislamiento obligatorio.
  - **A04:** `response.evaluated` lleva solo scores y referencias; prohibido texto de conversación.
  - **A09:** veredictos, reintentos, fallbacks, skips y cambios de modo auditados; la tasa de
    fallback es alarma operativa; el cambio enforce↔shadow queda registrado.
  - **A06:** el evaluador veta pero no edita ni mueve estados — se preserva el backstop "LLM no
    autoritativo".
