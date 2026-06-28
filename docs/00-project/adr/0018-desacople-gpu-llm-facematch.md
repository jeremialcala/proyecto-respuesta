# ADR-0018: Desacople del plano GPU LLM ↔ FaceMatch (worker dedicado escalado por cola)

- **Estado:** proposed
- **Fecha:** 2026-06-28
- **Decisores:** Jeremi
- **Fase AI-DLC:** 05-deployment
- **Controles OWASP afectados:** A04 (datos biométricos), A01 (acceso/IRSA), A05 (config), A08 (DLQ/resiliencia)
- **Relacionado:** [ADR-0001](0001-llm-on-premises.md) (LLM on-prem), [ADR-0012](0012-broker-aws-sqs-sns.md) (SQS/SNS), [ADR-0013](0013-arcface-scoring-solo-rostro.md) (enmienda la decisión abierta "GPU compartida con el LLM"), [ADR-0014](0014-contenedores-despliegue-eks.md) (KEDA por profundidad de cola, nodos GPU). Análisis de soporte: `factibilidad-offload-gpu-vastai.md`.

## Contexto

El [ADR-0013](0013-arcface-scoring-solo-rostro.md) fijó como decisión abierta del MVP que ArcFace/IResNet100 corre sobre la **RTX 3090 (24 GB) on-prem compartida con el LLM** ([ADR-0001](0001-llm-on-premises.md)), aceptando que "bajo pico compite con el LLM por la GPU". En operación esa contención se vuelve el cuello de botella: la inferencia LLM mantiene VRAM (KV-cache) y es sensible a latencia conversacional, mientras el facematch llega en **ráfagas batch** tras un evento (réplica → ola de reportes) y quiere saturar la GPU. Conviviendo en la misma GPU, o la LLM sufre jitter, o el facematch serializa; y **escalar una carga obliga a escalar la otra**, porque comparten el mismo equipo.

El `matching-worker` ya está diseñado como **worker dirigido por cola** con `KEDA ScaledObject` que escala por **profundidad de la cola** SQS sobre nodos GPU ([ADR-0014](0014-contenedores-despliegue-eks.md)). Lo que falta es **separar el plano de cómputo GPU del facematch del de la LLM**, para que cada carga escale por su propia métrica y no se degraden mutuamente. Esta es una precondición de cualquier estrategia de elasticidad (incluido el burst a GPU on-demand del [ADR-0019]) y, según el análisis de factibilidad, resuelve la contención por sí sola.

## Decisión

**1. Planos GPU separados.** El facematch (ArcFace: detección + alineación + embedding) deja de compartir GPU con el LLM. El LLM conserva su GPU on-prem ([ADR-0001](0001-llm-on-premises.md)); el facematch obtiene **capacidad GPU propia y dedicada**, dimensionada por su propia métrica de carga. Ningún proceso de inferencia LLM y de ArcFace vuelve a co-residir en la misma GPU física.

**2. El facematch como servicio worker autónomo, sin estado.** Se consolida el `matching-worker` de inferencia como pool **stateless** que:
- **consume trabajo del broker** SQS/SNS ([ADR-0012](0012-broker-aws-sqs-sns.md)) — no expone puerto HTTP;
- ejecuta el pipeline ArcFace ([ADR-0013](0013-arcface-scoring-solo-rostro.md)) y **publica embeddings/eventos** de vuelta al bus (`match.evaluado`, contrato [ADR-0011]);
- es **idempotente y re-encolable**: con *visibility timeout* + DLQ por redrive ([ADR-0012]/[ADR-0014]), un pod que muera (o una GPU que se reclame) reprocesa sin pérdida ni doble efecto.

> Se separa explícitamente la **extracción de embedding** (GPU-bound, lo que aquí se escala/aísla) del **matching/scoring** (búsqueda ANN sobre pgvector+FAISS, CPU-bound, <10 ms) que **permanece en-región** y no migra de plano. La GPU solo transforma imagen→vector.

**3. Escalado independiente por profundidad de cola.** El pool de facematch escala con `KEDA` por la **profundidad de su cola** (no por CPU, no acoplado al LLM): mínimo caliente para latencia baja, máximo para drenar olas. El LLM mantiene su propio dimensionamiento.

**4. Capacidad base flexible en proveedor.** La capacidad GPU base del facematch puede ser un **segundo GPU on-prem dedicado** o **nodos GPU en AWS sa-east-1** ([ADR-0006]/[ADR-0014]); la imagen y los manifiestos se mantienen **portables** (principio de [ADR-0014]) para no acoplar la decisión a un único proveedor. El burst elástico a GPU on-demand de terceros se trata en el [ADR-0019].

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Planos GPU separados + worker por cola** ✅ | Elimina la contención; cada carga escala por su métrica; sin reescritura (KEDA ya existe); portable | Requiere GPU dedicada extra (on-prem o cloud) → costo | Sin cambio: biométrico (A04) ya contenido en-región |
| **B. Status quo: GPU compartida con time-slicing/MPS** | Sin GPU extra; cambio mínimo | El jitter del LLM y la serialización del facematch persisten bajo pico; escalado sigue acoplado | El pico puede degradar disponibilidad (A08) |
| **C. Mover ArcFace a CPU (fallback SFace, ADR-0013/B)** | Libera la GPU del LLM sin GPU extra | Precisión por debajo de SOTA → sube T2 (falso positivo, el peor riesgo); throughput pobre en video | Mayor T2 con datos difíciles |
| **D. Mover el LLM a cloud y dedicar la 3090 al facematch** | Una sola GPU dedicada al FM | Contradice [ADR-0001] (LLM on-prem) y su base legal/coste; gran cambio | Reabre decisiones de [ADR-0001] |

## Consecuencias

- **Positivas:** desaparece la contención LLM↔FaceMatch (la latencia conversacional se estabiliza); el facematch escala horizontalmente con la ola por profundidad de cola; arquitectura sin estado, idempotente y resiliente (DLQ); base lista para el burst on-demand del [ADR-0019]; sin reescritura del worker (se reutiliza KEDA/SQS de [ADR-0014]).
- **Negativas / deuda asumida:** se necesita **capacidad GPU dedicada adicional** para el facematch (segundo equipo on-prem o nodos GPU cloud) → costo e infra; hay que **revisar la decisión abierta de [ADR-0013]** ("3090 compartida") y actualizar manifiestos/`nodeSelector`/KEDA para el pool dedicado; aparece latencia de **cold-start** al escalar desde el mínimo (mitigable con pool caliente).
- **Impacto en threat model:**
  - **A08 (resiliencia):** aislar el facematch evita que una ola tumbe la disponibilidad del LLM y viceversa; DLQ + idempotencia preservan el trabajo ante muerte de pod/reclamo de GPU.
  - **A04 (biométrico):** el embedding/matching y la galería **siguen en-región** ([ADR-0006]); este ADR no cambia dónde residen los datos (eso lo aborda el [ADR-0019]).
  - **T2 (falso positivo):** se conserva ArcFace SOTA (no se degrada a CPU/SFace salvo fallback explícito).

## Decisiones abiertas

- `<TODO>` Ubicación de la **capacidad GPU base** del facematch: segundo GPU on-prem dedicado vs nodos GPU en AWS sa-east-1 (coste vs residencia vs ops).
- `<TODO>` Tamaño del **pool caliente mínimo** (latencia objetivo de la primera respuesta tras inactividad) y umbrales KEDA (profundidad de cola → réplicas).
- `<TODO>` Métrica/SLO de la cola de facematch (profundidad y antigüedad máximas aceptables antes de escalar/alertar).
- `<TODO>` Política de prioridad de cola (reportes en vivo vs reprocesos batch) si comparten pool.

## Disparadores de revisión

- El costo de la GPU dedicada base supera al de consolidar en on-prem híbrido → reevaluar topología.
- La profundidad de cola en picos excede lo que la base absorbe en el SLO → activar burst on-demand ([ADR-0019]).
- Aparece una carga GPU adicional (p. ej. detección de duplicados a escala) que justifique su propio plano.
