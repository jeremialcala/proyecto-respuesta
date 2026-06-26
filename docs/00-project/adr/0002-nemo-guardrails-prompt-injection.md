# ADR-0002: Mitigación de prompt injection con NeMo Guardrails

- **Estado:** accepted
- **Fecha:** 2026-06-25
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A05 (injection), `ai-sec`, A06 (insecure design), A09 (logging)
- **Relacionado:** [ADR-0001](0001-llm-on-premises.md) (LLM on-premises), RS-13, AB-07, AB-15

## Contexto

El chatbot recibe mensajes de **redes de mensajería no confiables** (WhatsApp/IG/Messenger/Telegram)
y los pasa al **LLM on-premises** (ADR-0001) que conversa, extrae reportes y media el intercambio.
Esa entrada no confiable hacia un LLM con capacidad de mediar es la superficie principal de
**prompt injection** (RS-13, AB-07; y AB-15 si el LLM se desviara de su rol). Necesitamos una capa
de guardarraíles **programable y auditable** que viva dentro de la frontera (sin proveedor externo).

> Premisa honesta: el prompt injection **no tiene mitigación absoluta** hoy; es un problema abierto.
> El objetivo es **defensa en profundidad**, no una garantía. El backstop no es el guardrail sino la
> arquitectura: el LLM **no es autoritativo** y no puede mover estados, así que una inyección que
> burle los rieles tampoco dispara una acción de alto costo.

## Decisión

Adoptamos **NeMo Guardrails** (open-source, self-hostable, rieles en Colang) como capa de
guardarraíles alrededor del orquestador LLM, integrada con el modelo local (Ollama). Se definen:

- **Input rails** — detección de jailbreak/inyección, normalización, chequeos de PII y de formato
  sobre el mensaje entrante **antes** de llegar al LLM.
- **Topical / dialogue rails** — mantienen la conversación dentro del dominio de reporte; el LLM no
  sigue instrucciones que lo saquen de su rol.
- **Output rails** — validan la salida del LLM: estructura esperada, sin fuga de datos, sin intentar
  ejecutar acciones; lo que mueve estados pasa por el motor determinista + humano, no por el LLM.
- **Restricción de tool-use** — el LLM no tiene herramientas que cambien estado (refuerza
  "LLM no autoritativo").

**Optimización de costo/latencia** (contexto masivo + sin funding, ADR-0001): **rieles heurísticos
primero** (regex, allowlist, longitud, idioma) que son baratos; reservar los rieles que invocan al
LLM (self-check, jailbreak) para caminos de mayor riesgo, o usar un **modelo guardián pequeño**
dedicado. Evitar que cada mensaje cueste 2-3 inferencias por defecto.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. NeMo Guardrails** ✅ | Open-source y self-hostable (alinea ADR-0001); rieles declarativos y **auditables** en Colang; input/output/topical/dialogue; integra con modelos locales; comunidad activa | Curva de Colang; rieles con LLM añaden latencia/costo; mantenimiento de los rieles; falsos positivos posibles | Reduce A05; requiere logging de disparos (A09); no elimina el riesgo (defensa en profundidad) |
| **B. Rieles heurísticos propios (regex/allowlist)** | Muy baratos y rápidos; sin dependencia nueva | Cobertura limitada; frágiles ante ataques nuevos; reinventar lo que NeMo ya da | Cobertura insuficiente como única defensa |
| **C. Moderación gestionada (API de proveedor)** | Lista para usar, mantenida por terceros | **Contradice on-prem/privacidad** (PII a tercero); costo por llamada; dependencia externa | Exposición de datos (A04); choca con ADR-0001 |
| **D. Guardrails AI (OSS alternativo)** | Validación de salida estructurada robusta | Menos foco en rieles conversacionales/jailbreak que NeMo | Cobertura parcial del vector conversacional |

> La opción B no se descarta: se **combina** con A como primera línea barata (rieles heurísticos →
> rieles NeMo solo cuando hace falta).

## Consecuencias

- **Positivas:** capa anti prompt-injection **auditable** y dentro de la frontera; rieles de salida
  que impiden fuga y acciones indebidas; defensa en profundidad junto al guardarraíl arquitectónico
  (LLM no autoritativo); sin enviar datos a un moderador externo.
- **Negativas / deuda asumida:** latencia y **costo de inferencia** extra si se abusa de rieles con
  LLM (mitigado con heurísticos-primero / modelo guardián pequeño); mantenimiento continuo de los
  rieles Colang; falsos positivos que pueden frenar reportes legítimos (calibrar).
- **Impacto en threat model:**
  - **A05 / `ai-sec`:** baja la probabilidad de inyección exitosa; trazar RS-13 a este control.
  - **A06 (insecure design):** formaliza la defensa en profundidad del canal conversacional.
  - **A09:** los disparos de rieles se registran para auditoría y red-teaming.

## Disparadores de revisión

- Aparecen vectores de inyección que burlan los rieles → ampliar/red-team los rieles.
- La latencia de los rieles con LLM degrada el SLO bajo pico → mover más lógica a heurísticos o a un
  modelo guardián pequeño.
- Cambia el modelo local (ADR-0001) → revalidar los rieles contra el nuevo modelo.
