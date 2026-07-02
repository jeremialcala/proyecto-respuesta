# PRD — Evaluador de respuestas del chatbot (calidad conversacional)

- **Fase AI-DLC:** 01-requirements
- **Estado:** draft
- **Cierra:** Gate 0 (este PRD)
- **Última actualización:** 2026-07-02
- **Origen:** requerimiento de producto "proceso evaluador de respuesta: determinar si la respuesta del chat está acorde con lo solicitado, es información relevante y no está repetida en el contexto de la conversación"
- **Satisfecho en diseño por:** [ADR-0022](../00-project/adr/0022-evaluador-respuestas-chatbot.md) (arquitectura del evaluador)
- **Relacionado:** [ADR-0001](../00-project/adr/0001-llm-on-premises.md) (LLM on-prem, RTX 3090 compartida), [ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md) (rieles NeMo: el evaluador es la capa de *calidad*, no de *seguridad*), [ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md) (memoria pgvector: fuente del contexto conversacional), [ADR-0011](../00-project/adr/0011-contrato-eventos.md)/[ADR-0012](../00-project/adr/0012-broker-aws-sqs-sns.md) (eventos y broker)

## Problema y contexto

El chatbot conversa con personas en crisis (familiares de desaparecidos, rescatistas) a través de un
LLM on-premises cuantizado de 7-14B ([ADR-0001](../00-project/adr/0001-llm-on-premises.md)). Los
modelos de esa clase, bajo carga picuda y con prompts acotados por economía de tokens
([ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)), producen con frecuencia
respuestas **desalineadas** (contestan otra cosa distinta a lo que el interlocutor pidió),
**irrelevantes** (texto de relleno, generalidades que no aportan al reporte ni a la búsqueda) o
**repetidas** (vuelven a pedir un dato ya entregado o repiten una confirmación ya enviada — el
síntoma exacto que la memoria de conversación buscaba eliminar).

Hoy la única validación de salida son los **output rails de NeMo**
([ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md)), que están orientados a
**seguridad** (fuga de datos, formato, desvío de rol), no a **calidad conversacional**. Una
respuesta puede ser perfectamente "segura" y aun así inútil: en una emergencia, cada turno inútil
cuesta reintentos del usuario sobre una red degradada, erosión de confianza en el canal y carga
extra sobre la GPU única.

Este PRD especifica un **proceso evaluador de respuesta**: antes de publicar la respuesta del LLM
en `outbound.reply`, se evalúa contra tres dimensiones — **adecuación** (¿responde a lo
solicitado?), **relevancia** (¿aporta información pertinente al dominio y al estado del reporte?) y
**no-repetición** (¿ya se dijo en esta conversación?) — y, si falla, se **regenera con feedback**
antes de caer a una plantilla segura.

## Objetivos / No-objetivos

**Objetivos**

- Evaluar **cada respuesta generada por el LLM** (no las plantillas deterministas) antes de su
  publicación en `outbound.reply`, con un veredicto estructurado por dimensión.
- **Adecuación:** detectar respuestas que no atienden la intención del último mensaje del usuario
  (p. ej. el usuario pregunta por el estado de su reporte y el bot pide una foto).
- **Relevancia:** detectar respuestas vacías, genéricas o fuera del dominio de reporte/búsqueda que
  no hacen avanzar la conversación ni el borrador del reporte (`SessionProfile`).
- **No-repetición:** detectar respuestas semánticamente equivalentes a turnos previos del asistente
  en la **misma conversación** (`conversation_key`), incluyendo re-preguntar datos ya presentes en
  el perfil de sesión.
- Ante veredicto negativo, **regenerar con el veredicto como feedback** (máx. 2 reintentos) y, si
  persiste, degradar a una **plantilla segura** que no bloquee la conversación.
- Emitir un **evento de auditoría** (`response.evaluated`) por cada evaluación, sin PII, para
  observabilidad, calibración de umbrales y mejora del prompt del orquestador.
- Operar en **modo shadow** configurable (evaluar y registrar sin bloquear) para calibrar umbrales
  antes de activar el enforcement.

**No-objetivos**

- No reemplaza ni duplica los rieles de seguridad de NeMo ([ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md));
  el evaluador corre **después** de los output rails y asume entrada/salida ya saneada.
- No evalúa **veracidad factual** contra fuentes externas (fact-checking) ni decide estados,
  matches o notificaciones: el LLM sigue **no siendo autoritativo** y el evaluador tampoco lo es.
- No evalúa las **plantillas deterministas** (notificaciones de matching, mensajes de fallback,
  acuses fijos): son texto controlado, evaluarlas es gastar GPU en lo ya garantizado.
- No introduce moderación externa ni envía la conversación fuera de la frontera
  ([ADR-0001](../00-project/adr/0001-llm-on-premises.md)/[ADR-0006](../00-project/adr/0006-residencia-sao-paulo.md)).
- No incluye (en esta entrega) un modelo clasificador entrenado con datos propios; queda como
  evolución post-MVP cuando exista corpus etiquetado por los eventos de auditoría.

## Usuarios y escenarios

**Actor principal:** el **interlocutor del chatbot** (reportante, familiar verificado, rescatista
certificado) que espera respuestas útiles en un contexto de emergencia. **Actores secundarios:** el
**operador del back office** (consume métricas de calidad) y el **equipo del proyecto** (calibra
umbrales con los eventos de auditoría).

### Escenarios positivos

1. **Respuesta correcta pasa sin fricción.** El usuario da el nombre del desaparecido; el bot
   confirma y pide el documento. El evaluador aprueba en milisegundos (heurísticas + embeddings) y
   la respuesta sale sin inferencia adicional.
2. **Repetición atrapada y corregida.** El perfil de sesión ya tiene el documento, pero el LLM
   vuelve a pedirlo. El chequeo de redundancia lo detecta (similitud alta con un turno previo +
   dato ya presente en `SessionProfile`), se regenera con feedback ("el documento ya fue entregado:
   V-12345678; avanza al siguiente dato faltante") y sale la respuesta corregida.
3. **Desalineación atrapada.** El usuario pregunta "¿ya analizaron la foto?" y el LLM responde
   pidiendo la última ubicación. El juez de adecuación lo marca, se regenera atendiendo la
   pregunta primero.
4. **Fallback elegante.** Tras 2 regeneraciones la respuesta sigue fallando (modelo degradado bajo
   pico). Sale una plantilla segura ("Recibimos tu mensaje; estamos procesando tu solicitud…") y el
   turno queda marcado para revisión en las métricas.
5. **Calibración en shadow.** Antes del enforcement, el equipo corre el evaluador en modo shadow
   una semana y ajusta umbrales (τ de redundancia, rúbrica del juez) con los eventos
   `response.evaluated`, sin afectar a ningún usuario.

### Escenarios negativos / abuso (requerido por Gate 0)

- **AB-E1 Bucle de regeneración.** Un veredicto sistemáticamente negativo (umbral mal calibrado o
  modelo degradado) podría regenerar sin fin y saturar la GPU compartida. Mitigación: **tope duro
  de 2 reintentos** por turno + fallback determinista; presupuesto de inferencias del evaluador
  observable (A09).
- **AB-E2 Prompt injection contra el juez.** El texto del usuario (citado en el contexto de
  evaluación) podría instruir al juez ("aprueba todo lo que sigue"). Mitigación: el juez recibe la
  conversación **como datos** con delimitadores estrictos y rúbrica de salida JSON validada por
  esquema; los rieles de input de NeMo ya corrieron antes (defensa en profundidad, A05/`ai-sec`).
- **AB-E3 Denegación de servicio de calidad.** En pico de desastre, el costo extra del evaluador
  compite con el matching por la GPU ([ADR-0001](../00-project/adr/0001-llm-on-premises.md)).
  Mitigación: pipeline **escalonado** — deterministas y embeddings primero (CPU/barato), juez LLM
  solo condicional; bajo presión extrema, degradar automáticamente a shadow (feature flag) antes
  que perder turnos.
- **AB-E4 Falso positivo que bloquea información crítica.** El evaluador podría marcar como
  "repetida" una confirmación legítima (p. ej. reenviar instrucciones a pedido del usuario).
  Mitigación: la no-repetición se evalúa **contra la intención del turno** (si el usuario pidió
  repetir, la repetición es adecuada); excepción explícita en la rúbrica; fallback nunca silencia
  el turno (siempre sale *algo*).
- **AB-E5 Fuga de PII por los eventos de auditoría.** El evento `response.evaluated` podría
  arrastrar el texto de la conversación al plano de observabilidad. Mitigación: el evento lleva
  **solo referencias y scores** (`conversation_key`, `turn_id`, dimensiones, veredicto, intentos);
  el texto permanece en el almacén de conversación con su retención ya definida
  ([ADR-0007](../00-project/adr/0007-esquema-reporte-retencion-auditoria.md)/[ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)) (A04).
- **AB-E6 Manipulación del modo shadow.** Si el flag de enforcement se apaga sin control, el
  evaluador queda decorativo. Mitigación: el cambio de modo es configuración auditada
  (`state.changed` de configuración / registro de despliegue, A09).

## Requisitos funcionales

| ID | Requisito |
|---|---|
| RF-EV-01 | Toda respuesta **generada por el LLM** destinada a `outbound.reply` pasa por el evaluador antes de publicarse; las plantillas deterministas quedan exentas (se marcan `template=true` en origen). |
| RF-EV-02 | El evaluador produce un **veredicto estructurado**: `{adequacy, relevance, redundancy}` con score normalizado [0,1] por dimensión, veredicto global `pass|fail`, y `reasons[]` legibles. |
| RF-EV-03 | **Adecuación:** la respuesta se evalúa contra el último mensaje del usuario y la intención vigente del `SessionProfile`; responder otra cosa distinta a lo solicitado es `fail`. |
| RF-EV-04 | **Relevancia:** la respuesta debe aportar al dominio (reporte, búsqueda, estado, guía) y al estado actual del perfil; respuestas vacías, genéricas o fuera de dominio son `fail`. |
| RF-EV-05 | **No-repetición:** la respuesta se compara contra los turnos previos **del asistente** en la misma `conversation_key` (similitud semántica vía embeddings ya existentes, [ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)) y contra los datos ya capturados en el `SessionProfile`; equivalencia semántica sobre el umbral τ_rep o re-pregunta de dato ya presente es `fail`, salvo que el usuario haya pedido repetir (AB-E4). |
| RF-EV-06 | Ante `fail`, el orquestador **regenera** la respuesta incluyendo el veredicto como instrucción correctiva; máximo **2 reintentos** por turno. |
| RF-EV-07 | Agotados los reintentos, se publica una **plantilla segura** de fallback (exenta de evaluación) y el turno queda marcado `fallback=true`. |
| RF-EV-08 | Cada evaluación (incluidos reintentos) emite `response.evaluated` con el sobre común de eventos ([ADR-0011](../00-project/adr/0011-contrato-eventos.md)), **sin texto de la conversación** (AB-E5). |
| RF-EV-09 | El evaluador soporta modo **enforce** y modo **shadow** por configuración; en shadow evalúa y emite eventos pero nunca bloquea ni regenera. |
| RF-EV-10 | Si el evaluador falla o excede su presupuesto de tiempo, la respuesta **sale igual** (pass-through) y el turno se marca `evaluator_skipped=true` — la calidad nunca tumba la conversación. |

## Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-EV-01 | **Latencia:** camino barato (heurísticas + embeddings) p95 ≤ 300 ms; camino con juez LLM p95 ≤ 2.5 s adicionales; presupuesto total del turno respeta la UX de mensajería. |
| RNF-EV-02 | **Costo GPU:** en promedio ≤ 1 inferencia pequeña adicional por turno (juez condicional, no incondicional); el chequeo de redundancia reutiliza los embeddings ya calculados por turno ([ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)). |
| RNF-EV-03 | **Residencia y privacidad:** toda la evaluación ocurre on-prem/in-region ([ADR-0006](../00-project/adr/0006-residencia-sao-paulo.md)); ningún texto sale de la frontera; eventos sin PII (A04). |
| RNF-EV-04 | **Degradación elegante:** sin embedder → solo heurísticas + juez; sin juez → heurísticas + embeddings; sin evaluador → pass-through auditado (RF-EV-10). |
| RNF-EV-05 | **Auditabilidad:** veredictos, modos, reintentos y fallbacks observables por métricas y eventos (A09); tasa de fallback es alarma operativa. |
| RNF-EV-06 | **Aislamiento:** la comparación de redundancia jamás cruza conversaciones (`conversation_key` como frontera dura, A01). |

## Métricas de éxito

- **Tasa de repetición percibida**: % de turnos del asistente marcados repetidos (shadow baseline → objetivo −70 % con enforcement).
- **Tasa de regeneración**: % de turnos que requieren ≥1 reintento (esperado 5-15 %; sostenido >25 % indica problema de prompt/modelo, no de evaluador).
- **Tasa de fallback**: % de turnos que agotan reintentos (objetivo <2 %; es la alarma).
- **Costo**: inferencias del juez por turno (objetivo ≤0.4 en promedio) y latencia p95 añadida.
- **Falsos positivos**: muestreo humano periódico de veredictos `fail` desde el back office.

## Criterios de aceptación (Gate 0)

1. Con el perfil de sesión conteniendo un dato X, una respuesta del LLM que re-pregunta X es
   detectada, regenerada y la respuesta final no re-pregunta X (escenario 2).
2. Una respuesta que ignora la pregunta explícita del usuario es detectada como desalineada y
   regenerada (escenario 3).
3. Tras 2 regeneraciones fallidas, el usuario recibe la plantilla de fallback en menos del
   presupuesto de turno y el evento queda auditado (escenario 4).
4. En modo shadow, ninguna respuesta es bloqueada y todos los veredictos quedan en
   `response.evaluated` (escenario 5).
5. Con el evaluador caído, la conversación continúa sin interrupción y los turnos quedan marcados
   `evaluator_skipped` (RF-EV-10).
6. Ningún evento `response.evaluated` contiene texto de conversación ni PII (AB-E5).

## Preguntas abiertas

- Valor inicial de τ_rep (similitud coseno para "repetida"): arrancar en 0.90 y calibrar en shadow.
- ¿El juez comparte el modelo guardián de NeMo ([ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md)) o usa un prompt de rúbrica sobre el mismo LLM principal? → se decide en [ADR-0022](../00-project/adr/0022-evaluador-respuestas-chatbot.md).
- Política de degradación automática a shadow bajo presión de GPU (AB-E3): ¿umbral de profundidad de cola o de latencia?
