# ADR-0019: Imagen de inferencia ArcFace portable (TensorRT pre-compilado) para burst en GPU on-demand (vast.ai)

- **Estado:** proposed
- **Fecha:** 2026-06-28
- **Decisores:** Jeremi
- **Fase AI-DLC:** 05-deployment
- **Controles OWASP afectados:** A04 (biométrico a sub-procesador), A05 (config/secretos), A02 (hardening), A08 (resiliencia/interrupción), `ai-sec`
- **Relacionado:** [ADR-0006](0006-residencia-sao-paulo.md) (residencia sa-east-1), [ADR-0008](0008-boveda-llaves-identidad.md) (Vault/secretos), [ADR-0011](0011-contrato-eventos.md) (contrato de eventos), [ADR-0012](0012-broker-aws-sqs-sns.md) (SQS/SNS), [ADR-0013](0013-arcface-scoring-solo-rostro.md) (ArcFace/IResNet100), [ADR-0014](0014-contenedores-despliegue-eks.md) (imágenes OCI/EKS), [ADR-0018](0018-desacople-gpu-llm-facematch.md) (plano GPU separado). Análisis de soporte: `factibilidad-offload-gpu-vastai.md`.

> **Estado de implementación (sigue `proposed`).** Realizada la **arquitectura portable** (prerrequisito
> no negociable): plano de inferencia stateless con su **imagen OCI dedicada** (`Dockerfile.inference`,
> entrypoint `matching_worker.inference_main`), **contrato efímero** `face.extract.requested` →
> `face.embedded` (solo-vector), y **extractor seleccionable por configuración** (`FACE_EXTRACTOR=local|
> remote`) en el worker in-region — el mismo flujo corre local o remoto sin reescritura. Manifiestos K8s
> `deploy/k8s/inference-worker/` (restricted, **sin secretos**, pool GPU `facematch`, KEDA por cola).
> **Pendiente (decisiones abiertas, gating del egress real):** baking del engine **TensorRT**, **PoC**
> en vast.ai con datos sintéticos, **validación legal** de residencia + registro de sub-procesador,
> **disparador del burst** (KEDA→API vast.ai) y **tokens de corta vida** hacia nodos efímeros.

## Contexto

Con el plano GPU del facematch ya separado del LLM ([ADR-0018]), falta una estrategia de **elasticidad ante picos**: tras un evento, la cola de facematch puede crecer por encima de lo que absorbe la capacidad base en el SLO. La capacidad GPU en-región ([ADR-0006]/[ADR-0014]) es la base de cumplimiento, pero dimensionarla para el peor pico es caro y desaprovechado el 99 % del tiempo.

El análisis de factibilidad (`factibilidad-offload-gpu-vastai.md`) concluye que **burstear a GPU on-demand de terceros (vast.ai) es viable** para esta carga —batch, sin estado, "embarrassingly parallel"— **si y solo si** (a) se usa la capa **Secure Cloud / hosts verificados** (ISO 27001, GDPR DPA, vast.ai con SOC 2 Type 2), no el marketplace abierto; (b) se aplica **procesamiento efímero** que devuelve solo el vector; y (c) la decisión es compatible con la postura "flexible con controles" sobre residencia (la biometría puede procesarse fuera de São Paulo *con* mitigaciones). El costo de cómputo es marginal; el valor es **absorber ráfagas** sin sobredimensionar la base.

Para que la misma carga corra indistintamente en EKS sa-east-1, on-prem o vast.ai, se necesita una **imagen de inferencia portable, sin estado y con el motor TensorRT pre-compilado** (el cold-start de compilar el engine en cada arranque es inaceptable para escalado elástico).

## Decisión

**1. Imagen de inferencia ArcFace dedicada, sin estado, con TensorRT pre-compilado.** Se separa una imagen OCI de inferencia (distinta de la imagen de control del worker) que:
- contiene el pipeline de [ADR-0013] (detector InsightFace + ArcFace/IResNet100) servido con **TensorRT** y el **engine ya compilado y horneado** en la imagen (o en un volumen de solo lectura), evitando recompilación en arranque;
- es **stateless**: recibe trabajo, procesa, devuelve resultado, no persiste nada en disco del host;
- corre como **contenedor no-root, restricted** (alineado con [ADR-0014]: `runAsNonRoot`, `readOnlyRootFilesystem`, `drop: [ALL]`, `seccompProfile`).

**2. Primariamente diseñada para vast.ai, pero portable.** La imagen se optimiza y valida para **vast.ai Secure Cloud** como destino principal de burst, **sin acoplarse** a él: la misma imagen corre en nodos GPU de EKS sa-east-1 y on-prem (principio de portabilidad de [ADR-0014]). La selección de destino es **configuración**, no código.

**3. Solo Secure Cloud, región Brasil, hosts verificados.** Queda **prohibido** el marketplace abierto/no verificado para esta carga. Se filtra por datacenters verificados (ISO 27001/GDPR) y, preferentemente, **región Brasil** para minimizar distancia a la residencia de [ADR-0006]. Reliability mínima: > 0.95 (on-demand), > 0.90 (interruptible tolerable).

**4. Patrón de procesamiento efímero (minimización de datos).**
- El worker en-región **pre-recorta la cara / pre-muestrea frames de video** y envía **el mínimo** necesario para detección+embedding, cifrado en tránsito (TLS).
- El nodo on-demand **devuelve solo el embedding 512-d** vía el bus ([ADR-0011]/[ADR-0012]); **descarta la imagen** tras procesar; al destruir la instancia, vast.ai destruye los datos.
- El **matching/scoring, la galería, pgvector/FAISS y la Vault permanecen siempre en-región** ([ADR-0006]/[ADR-0008]). El nodo de terceros solo hace imagen→vector.
- **Sin secretos en el nodo**: no lleva credenciales a la Vault; recibe trabajo y devuelve resultado con **tokens de corta vida** ([ADR-0008]).

**5. Resiliencia ante interrupción.** Las instancias *interruptible* pueden reclamarse con minutos de aviso; por eso el consumo es **idempotente con re-encolado** (visibility timeout + DLQ, [ADR-0012]/[ADR-0018]). On-demand/reserved para la fracción sensible a latencia; interruptible solo para reprocesos de baja prioridad.

**6. Gobernanza de sub-procesador.** vast.ai (y su DC) se registran como **sub-procesador** en el DPA/base legal del proyecto; se valida con el marco legal que el "procesamiento efímero de imagen con retorno de solo-vector en DC verificado GDPR fuera de São Paulo" cae dentro de "flexible con controles". **Validación previa con datos sintéticos/consentidos antes de tráfico real.**

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Imagen portable TensorRT + burst a vast.ai Secure Cloud** ✅ | Elasticidad ante olas sin sobredimensionar la base; costo marginal; cold-start bajo (engine horneado); portable | Introduce sub-procesador de terceros; biométrico sale de la frontera (mitigado por efímero/solo-vector); ops de doble destino | **A04**: biométrico a 3.º → mitigado (Secure Cloud, efímero, solo-vector, sin persistencia) |
| **B. Solo capacidad GPU base en-región (sin burst)** | Residencia dura; sin sub-procesador | Pico mal absorbido o base sobredimensionada (cara) | Riesgo de disponibilidad (A08) en olas |
| **C. Burst a GPU gestionada del mismo cloud (sa-east-1, SageMaker async/serverless)** | Residencia dura; sin marketplace | 2–4× costo vs vast.ai; menos GPU disponible bajo demanda extrema | Bajo (mismo perímetro) |
| **D. Marketplace abierto de vast.ai (hosts no verificados)** | El más barato | Sin garantías de cumplimiento; biométrico en rigs sin auditar | **Inaceptable** (A04) |
| **E. API gestionada de reconocimiento (Rekognition/otros)** | Cero ops | Biométrico a un tercero como servicio; contradice on-prem/[ADR-0013]/[ADR-0008] | Exposición de biométrico — inaceptable |

> **C** queda como **alternativa de residencia dura**: si la validación legal no admite procesar fuera de São Paulo, el burst se hace en sa-east-1 (misma imagen, distinto destino). **D** y **E** descartadas.

## Consecuencias

- **Positivas:** la cola de facematch se drena en minutos durante una ola sin sobredimensionar la base; costo de burst marginal; misma imagen para EKS/on-prem/vast.ai (sin lock-in); cold-start bajo por engine TensorRT pre-compilado; controles de privacidad explícitos (efímero, solo-vector, en-región para galería/Vault).
- **Negativas / deuda asumida:** se introduce un **sub-procesador de terceros** con su carga legal (DPA, base legal, registro); **doble ruta operativa** (en-región + on-demand) que mantener y observar; build/push de imagen CUDA+TensorRT pesado; necesidad de **PoC** para medir cold-start, throughput, egress e interrupción reales; gestión de tokens de corta vida hacia nodos efímeros.
- **Impacto en threat model:**
  - **A04 (biométrico):** sale de la frontera bajo controles (Secure Cloud GDPR, efímero, solo-vector, sin persistencia, TLS); galería y Vault no salen. Residual: confianza en la destrucción de datos del DC al terminar la instancia.
  - **A05/A02:** sin secretos en imagen ni en nodo; contenedor restricted no-root.
  - **A08 (interrupción):** idempotencia + DLQ absorben reclamos de GPU; on-demand para lo sensible a latencia.
  - **`ai-sec` / T2:** el modelo es el mismo ArcFace de [ADR-0013]; el cambio de infra no altera precisión ni sesgo (se conserva no auto-confirmación + revisión humana).

## Decisiones abiertas

- `<TODO>` **PoC en vast.ai Secure Cloud (Brasil) con datos sintéticos**: medir cold-start real, throughput del pipeline, latencia/costo de egress e ingress, y tasa de interrupción.
- `<TODO>` **Validación legal** de la postura de residencia para procesamiento efímero fuera de São Paulo (base legal + actualización de DPA/sub-procesadores).
- `<TODO>` Distribución del engine TensorRT: horneado en la imagen vs volumen/registro de artefactos versionado (`model=arcface`, `version=iresnet100` — coherente con [ADR-0007]/[ADR-0013]).
- `<TODO>` Mecanismo de **disparo del burst** (KEDA por profundidad de cola → aprovisionar instancias vast.ai vía API) y orquestación del ciclo de vida (alta, salud, baja, destrucción de datos).
- `<TODO>` Política de **pre-recorte/pre-muestreo** en-región (qué mínimo se envía) y verificación de que ninguna imagen original completa cruza la frontera.
- `<TODO>` Emisión y alcance de **tokens de corta vida** para nodos efímeros (scopes mínimos, sin acceso a Vault).

## Disparadores de revisión

- La validación legal **no** admite procesar biometría fuera de São Paulo → conmutar el burst a **sa-east-1** (opción C, misma imagen).
- La tasa de interrupción o el cold-start del PoC degradan el SLO de la ola → más on-demand/reserved o más base en-región.
- vast.ai cambia su modelo de cumplimiento/Secure Cloud o retira presencia en Brasil → reevaluar proveedor de burst.
- El costo del burst on-demand supera al de ampliar la base en-región → consolidar capacidad base.
