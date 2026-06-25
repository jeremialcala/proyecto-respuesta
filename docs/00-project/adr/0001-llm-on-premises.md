# ADR-0001: LLM on-premises (Ollama + worker) vs. proveedor gestionado

- **Estado:** accepted
- **Fecha:** 2026-06-25
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A03 (supply chain), A04 (cryptographic/data), A09 (logging/monitoring), `ai-sec`

## Contexto

El chatbot (canal principal) necesita un LLM que: (1) convierta conversaciones de mensajería en
reportes estructurados, (2) medie el intercambio entre actores, y (3) genere notificaciones. El
servicio es **masivo**, **sin funding**, con **carga picuda** (un desastre concentra la demanda en
horas) y requiere **velocidad de procesamiento**. Además, ya decidimos privacidad por diseño
(Modelo A, contexto de persecución): la PII conversacional no debería salir de la frontera.

La decisión es cómo servir ese LLM: **self-hosted con Ollama detrás de una cola + pool de workers**,
o un **proveedor gestionado** (OpenAI u otro servicio de chat).

> El requisito de privacidad (PRD RF-01, RS-13, RS-15) ya empuja hacia on-premises. Este ADR fija el
> *cómo* y registra las consecuencias y la deuda asumida.

## Decisión

Adoptamos **LLM on-premises con Ollama**, fronteado por una **cola de mensajes + workers** que
gestionan el procesamiento. Se usan **modelos open cuantizados** (p. ej. Llama 3.x 8B / Mistral /
Qwen) suficientes para extracción estructurada y conversación templada. La cola **absorbe los
picos** sin perder mensajes; el throughput escala **horizontalmente** sumando workers.

Se documenta una **ruta de evolución**: si el throughput supera la zona cómoda de Ollama, migrar la
capa de serving a **vLLM/TGI** (batching continuo) conservando el patrón cola+worker.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Ollama + worker (self-hosted)** ✅ | PII no sale de la frontera (alinea Modelo A, sin procesador externo); **costo acotado** (sin pago por token; el gasto es infra, no escala con cada mensaje); resiliente (no depende de API externa durante la emergencia); sin filtros de safety ajenos que rechacen contenido sensible legítimo; control total, sin lock-in; cola+worker absorbe picos y degrada con elegancia | **Carga operativa real** (desplegar, escalar, monitorear, actualizar modelos, GPUs); hardware costoso 24/7 → depende de hardware donado/créditos; calidad de modelo open < GPT-4 class; Ollama no es el servidor de máximo throughput a escala (posible migración a vLLM); latencia sube bajo pico | Nueva superficie de supply chain (pesos de modelo + deps de serving) → A03; exige observabilidad propia del worker → A09; sin filtro del proveedor, la validación de prompt injection es 100% nuestra → A05/`ai-sec` |
| **B. Proveedor gestionado (OpenAI/otros)** | Cero ops; escala instantánea; baja latencia; modelos de máxima calidad; sin hardware | **PII a un tercero (US)** → contradice Modelo A y la decisión de privacidad; **costo por token sin techo** → inviable para servicio masivo sin funding con demanda picuda; **dependencia de API externa** → frágil cuando la conectividad ya está degradada; filtros de safety pueden rechazar contenido sensible legítimo; lock-in y cambios de precio/ToS | Exposición de datos a procesador externo (A04); dependencia de disponibilidad de terceros; requiere DPA, residencia y no-entrenamiento |
| **C. Self-hosted con vLLM/TGI desde el inicio** | Máximo throughput (batching continuo); mismas ventajas de privacidad que A | Mayor complejidad operativa inicial; sobre-ingeniería para el arranque sin funding | Igual que A, con más superficie de serving que asegurar |

## Consecuencias

- **Positivas:** la PII conversacional permanece dentro de la frontera (refuerza A04 y la decisión
  de Modelo A); el costo queda acotado a infraestructura y no explota con la demanda; el sistema es
  resiliente a caídas de proveedores externos; sin lock-in ni filtros ajenos; los picos se manejan
  con la cola sin pérdida de mensajes.
- **Negativas / deuda asumida:** se asume **carga operativa** significativa para un equipo sin
  funding; dependencia de **hardware donado o créditos**; **calidad de modelo** inferior a frontera
  (aceptable para el caso de uso); posible **re-arquitectura de serving** (Ollama → vLLM) si el
  throughput lo exige. La tensión "masivo + sin funding + velocidad" no se elimina: se equilibra
  trocando algo de latencia en pico por costo acotado y cero pérdida.
- **Impacto en threat model:**
  - **A03 (supply chain):** verificar origen e integridad de los pesos del modelo y lockear las
    dependencias del worker y de Ollama.
  - **A04 (data):** la conversación con PII se procesa in-frontier; reduce la exposición a terceros.
  - **A09 (monitoring):** la observabilidad del pool de workers y de la cola pasa a ser nuestra.
  - **`ai-sec` / A05:** sin filtro de un proveedor, la mitigación de prompt injection y la
    validación de salidas del LLM son responsabilidad propia (RS-13).

## Disparadores de revisión

- El throughput sostenido supera lo que Ollama maneja con latencia aceptable → evaluar vLLM/TGI (Opción C).
- Aparece funding estable → reevaluar el balance ops vs. costo.
- El caso de uso exige razonamiento de frontera que los modelos open no cubren.
