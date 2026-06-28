# PRD — Escalabilidad y elasticidad del procesamiento FaceMatch

- **Fase AI-DLC:** 01-requirements
- **Estado:** draft
- **Cierra:** Gate 0 (este PRD)
- **Última actualización:** 2026-06-28
- **Origen:** estudio de factibilidad `factibilidad-offload-gpu-vastai.md` (raíz del proyecto)
- **Satisfecho en diseño por:** [ADR-0018](../00-project/adr/0018-desacople-gpu-llm-facematch.md) (desacople de plano GPU), [ADR-0019](../00-project/adr/0019-imagen-inferencia-arcface-tensorrt-vastai.md) (imagen TensorRT portable + burst on-demand)

## Problema y contexto

El motor de matching usa **ArcFace/IResNet100, GPU-bound** ([ADR-0013](../00-project/adr/0013-arcface-scoring-solo-rostro.md)), y en el MVP comparte la **RTX 3090 on-prem con el LLM** ([ADR-0001](../00-project/adr/0001-llm-on-premises.md)). Estas dos cargas tienen perfiles opuestos: la inferencia LLM mantiene VRAM y es sensible a latencia conversacional, mientras el facematch llega en **ráfagas batch** tras un evento (réplica → ola de reportes con foto/video). Conviviendo en la misma GPU, o la latencia del LLM sufre *jitter*, o el facematch serializa; y **escalar una carga obliga a escalar la otra**. El resultado, observado en operación, es que el procesamiento se vuelve **inescalable bajo pico**, comprometiendo la métrica núcleo del producto: la *latencia de candidatos* near-real-time (ver `flujo-central.md`, RF-04/RF-14).

Este PRD formaliza, como requerimiento de la metodología, el atributo de calidad **escalabilidad/elasticidad** del procesamiento FaceMatch (imagen y video): aislar su cómputo del LLM y absorber ráfagas de forma elástica **sin sobredimensionar** la capacidad base y **sin debilitar** la residencia ni la privacidad del dato biométrico ([ADR-0006](../00-project/adr/0006-residencia-sao-paulo.md), [ADR-0008](../00-project/adr/0008-boveda-llaves-identidad.md)). No introduce capacidades de producto nuevas; condiciona **cómo** se ejecuta el matching ya especificado. Ver `docs/00-project/charter.md`, `glossary.md`, `data-classification.md`.

## Objetivos / No-objetivos

**Objetivos**

- **Aislar** el cómputo del facematch del LLM, de modo que el pico de una carga no degrade la otra.
- Escalar el facematch de forma **elástica por profundidad de cola**, con un mínimo caliente para latencia baja y un máximo para drenar olas.
- **Absorber olas post-evento** dentro del SLO de latencia de candidatos sin dimensionar la capacidad base para el peor pico.
- Permitir **burst a GPU on-demand de terceros** como capacidad elástica, **preservando** residencia y privacidad del biométrico mediante procesamiento efímero y minimización de datos.
- Mantener el procesamiento **portable** (mismo artefacto en región / on-prem / on-demand), sin lock-in.

**No-objetivos**

- Cambiar el modelo (ArcFace/IResNet100), umbrales o el invariante de no auto-confirmación ([ADR-0013](../00-project/adr/0013-arcface-scoring-solo-rostro.md), RF-06/RF-07).
- Mover el **matching/scoring ANN, la galería (pgvector/FAISS) o la Vault** fuera de la frontera de residencia ([ADR-0006]/[ADR-0008]): el cómputo elástico solo transforma imagen→vector.
- Usar **marketplace abierto / hosts no verificados** para datos biométricos.
- Resolver la latencia conversacional del LLM (es objeto de su propio dimensionamiento).

## Usuarios y escenarios

Actores: **Coordinador** y **Buscador** (sufren la latencia de candidatos si el pico no se absorbe), **Operación/SRE** (dimensiona, escala y observa), **DPO/Legal** (gobierna el sub-procesador y la residencia). Indirectos: las familias, cuya resolución depende de que la ola se procese a tiempo.

### Escenarios positivos

- **EP-E1 Ola post-réplica.** Tras una réplica entran miles de reportes con foto/video en minutos. La cola de facematch crece; el sistema escala el pool dedicado (base en región + burst on-demand) y **drena la ola dentro del SLO**, sin afectar la latencia del LLM/chatbot.
- **EP-E2 Valle nocturno.** Fuera de pico, el pool baja a su mínimo caliente: se conserva latencia baja para reportes esporádicos sin pagar capacidad ociosa.
- **EP-E3 Interrupción tolerada.** Un nodo on-demand es reclamado a mitad de un lote; el trabajo en vuelo **se re-encola y reprocesa** sin pérdida ni doble efecto (idempotencia + DLQ).
- **EP-E4 Residencia preservada en burst.** Durante una ola, parte de la detección/embedding corre en un DC verificado fuera de São Paulo; **solo el vector 512-d regresa**, la imagen se descarta, y galería/Vault nunca salen de la región.

### Escenarios negativos / abuso (requerido por Gate 0)

| ID | Escenario de abuso | Mitigación | OWASP |
| :---- | :---- | :---- | :---- |
| **AB-16** | **Denial-of-Wallet**: inundación de reportes/medios para disparar burst on-demand y provocar coste desbocado o agotar cuota de GPU. | Rate limiting y deduplicación de intake (RS-05); **topes de escalado y de gasto** por ventana; alertas de coste/profundidad de cola; degradación a solo capacidad base ante abuso. | A10, A06 |
| **AB-17** | **Exfiltración de biométrico** en el nodo de cómputo de terceros (lectura de imagen en tránsito o en disco del host). | Procesamiento **efímero** (solo-vector de retorno, sin persistencia), **TLS**, minimización (cara recortada/frames muestreados), DC verificado GDPR, destrucción de datos al terminar la instancia. | A04, A02 |
| **AB-18** | **Host malicioso/comprometido** que se hace pasar por capacidad legítima para capturar trabajo. | **Prohibido marketplace abierto**: solo hosts verificados (ISO 27001/GDPR) con reliability mínima; **sin secretos en el nodo** (tokens de corta vida, sin acceso a Vault); validación de origen del resultado. | A04, A08 |
| **AB-19** | **Envenenamiento por reproceso**: forzar reintentos para duplicar enrolamientos o alterar la galería desde resultados manipulados. | Idempotencia por `report_id`/`message_id`; la galería/Vault y el merge **reversible** permanecen en región bajo control (RF-11); auditoría encadenada (RS-06). | A06, A08 |

## Requisitos funcionales

- **RF-16 Aislamiento de cómputo FaceMatch.** La inferencia de facematch (detección + alineación + embedding ArcFace) **no comparte GPU física con el LLM**; corre en un plano de cómputo dedicado, dimensionado por su propia métrica de carga. Ver [ADR-0018](../00-project/adr/0018-desacople-gpu-llm-facematch.md).
- **RF-17 Escalado elástico por profundidad de cola.** El pool de facematch escala automáticamente según la **profundidad de su cola** (KEDA sobre SQS, [ADR-0012](../00-project/adr/0012-broker-aws-sqs-sns.md)/[ADR-0014](../00-project/adr/0014-contenedores-despliegue-eks.md)), entre un **mínimo caliente** (latencia baja en valle) y un **máximo** (drenado de olas), de forma independiente del LLM.
- **RF-18 Capacidad de burst on-demand.** Ante picos que la capacidad base no absorbe en el SLO, el sistema añade **capacidad GPU on-demand** de terceros como extensión del pool. El consumo es **idempotente y re-encolable**: una instancia reclamada o caída no produce pérdida ni doble efecto (visibility timeout + DLQ). Ver [ADR-0019](../00-project/adr/0019-imagen-inferencia-arcface-tensorrt-vastai.md).
- **RF-19 Procesamiento efímero y minimización en cómputo externo.** Cuando la detección/embedding corre fuera de la frontera de residencia, el nodo recibe **solo el mínimo** necesario (cara recortada / frames muestreados, cifrado en tránsito), **devuelve solo el embedding 512-d**, no persiste la imagen, y **el matching ANN, la galería (pgvector/FAISS) y la Vault permanecen en región** ([ADR-0006]/[ADR-0008]). El nodo no porta secretos ni accede a la Vault.
- **RF-20 Worker stateless portable.** El procesamiento se empaqueta como artefacto **sin estado y portable** (imagen OCI con motor TensorRT pre-compilado para cold-start bajo), ejecutable indistintamente en región (EKS sa-east-1), on-prem o GPU on-demand verificada, **seleccionable por configuración** sin cambios de código. Ver [ADR-0019].

## Requisitos de seguridad (mapeados a OWASP ASVS)

| Req | Descripción | ASVS | Nivel | OWASP Top 10:2025 |
| :---- | :---- | :---- | :---- | :---- |
| **RS-16** | **Gobierno de sub-procesador de cómputo**: el burst on-demand usa **solo datacenters verificados** (mínimo ISO 27001, GDPR/DPA); prohibido el marketplace abierto/no verificado para biométrico; registro del sub-procesador y base legal de residencia ("flexible con controles") validados antes de tráfico real. | V1, V14 | L2 | A04, A03 |
| **RS-17** | **Minimización y efímero en cómputo externo**: cara/frames mínimos, cifrado en tránsito (TLS), retorno **solo-vector**, sin persistencia en el host, destrucción de datos al terminar la instancia; **sin secretos en el nodo** (tokens de corta vida, sin acceso a Vault). | V6, V8, V14 | L3 | A04, A02 |
| **RS-18** | **Resiliencia ante interrupción**: el procesamiento elástico es idempotente con re-encolado (visibility timeout + DLQ por redrive); ninguna interrupción de instancia causa pérdida de trabajo ni doble efecto sobre la galería. | V7, V11 | L2 | A08 |
| **RS-19** | **Anti Denial-of-Wallet**: topes de escalado y de gasto por ventana, rate limiting/deduplicación de intake y alertas de coste/cola para que el abuso no dispare cómputo on-demand sin control; degradación a capacidad base. | V11 | L2 | A10, A06 |

## Métricas de éxito

- **Latencia de candidatos bajo pico (p95)** dentro del SLO objetivo durante una ola post-evento (métrica núcleo de `flujo-central.md`, ahora medida bajo carga).
- **Tiempo de drenado de cola** tras una ola (de profundidad máxima a vacío).
- **Profundidad y antigüedad máximas** de la cola de facematch antes de escalar/alertar.
- **Aislamiento efectivo**: ausencia de correlación entre la carga de facematch y el *jitter* de latencia del LLM/chatbot.
- **Eficiencia**: coste por ola y utilización media de GPU (evitar sobredimensionar la base).
- **Cero persistencia externa**: 0 imágenes/medios persistidos fuera de la frontera de residencia (auditable); 100 % de retornos como solo-vector.

## Dependencias y riesgos

- **Validación legal de residencia** para procesamiento efímero fuera de São Paulo (postura "flexible con controles"): condiciona RF-18/RF-19/RS-16. Mientras no se valide, el burst se limita a **sa-east-1** (alternativa de residencia dura, [ADR-0019]).
- **Disponibilidad de GPU verificada** (preferente región Brasil) en el proveedor on-demand → riesgo de capacidad bajo demanda extrema.
- **Cold-start** del motor TensorRT y latencia de transferencia (egress/ingress) → mitigado por engine pre-horneado + pool caliente; a confirmar en **PoC con datos sintéticos** (decisión abierta de [ADR-0019]).
- **Capacidad GPU base dedicada** (on-prem adicional vs nodos sa-east-1) → decisión abierta de [ADR-0018], con impacto en coste/ops.
- **Sesgo biométrico** (RS-13) y **falsos positivos de alto costo** (RF-07, AB-04) **no cambian**: este PRD no altera el modelo ni el invariante de revisión humana.

## Trazabilidad

| Requisito | Diseño que lo satisface |
| :---- | :---- |
| RF-16 (aislamiento) | ADR-0018 |
| RF-17 (escalado por cola) | ADR-0018 (sobre KEDA de ADR-0014/0012) |
| RF-18 (burst on-demand) | ADR-0019 |
| RF-19 (efímero/minimización) | ADR-0019 (sobre ADR-0006/0008) |
| RF-20 (worker portable) | ADR-0019 (sobre ADR-0014) |
| RS-16…RS-19 | ADR-0019 (RS-16/17), ADR-0018 (RS-18), intake RS-05 + ADR-0019 (RS-19) |

## Estado de Gate 0 (este PRD)

| Criterio Gate 0 | Estado |
| :---- | :---- |
| Problema y contexto | ✅ |
| Objetivos / No-objetivos | ✅ |
| Requisitos funcionales | ✅ RF-16…RF-20 |
| Requisitos de seguridad → OWASP ASVS | ✅ RS-16…RS-19 |
| Escenarios negativos / abuso | ✅ AB-16…AB-19 |
| Threat assessment | ✅ Matriz de abuso trazada a OWASP; STRIDE/DREAD formal se actualiza en 02-design (Gate 1) junto a ADR-0018/0019 |
| Trazabilidad a diseño | ✅ ADR-0018, ADR-0019 |
