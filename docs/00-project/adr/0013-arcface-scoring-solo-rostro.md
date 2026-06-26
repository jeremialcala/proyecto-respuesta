# ADR-0013: Motor de embedding ArcFace/IResNet100 y scoring solo-rostro en MVP (enmienda ADR-0004)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A04 (datos biométricos), A06 (insecure design), `ai-sec` (sesgo)
- **Relacionado:** [ADR-0004](0004-motor-de-matching.md) (motor de embedding y fusión enmendados), RF-04/RF-14/RF-15, threat model T2/T10, [ADR-0007](0007-esquema-reporte-retencion-auditoria.md) (pgvector)

## Contexto

El [ADR-0004](0004-motor-de-matching.md) eligió **OpenCV YuNet (detección) + SFace (embedding ~128-d)**
honrando un requisito de "usando OpenCV", dejando **InsightFace/ArcFace como ruta de evolución
(opción C)** si la precisión de SFace resultaba insuficiente. Se decide adoptar esa ruta **desde el
MVP**: la calidad del reconocimiento es crítica porque un falso positivo notificado a una familia es
el riesgo más grave del producto (T2), y las condiciones de desastre (fotos viejas, mala luz, drift
de edad) exigen el mejor backbone disponible. Además, para el MVP se simplifica el scoring a
**solo-rostro**.

> Esta decisión **enmienda** las secciones de *embedding* y *fusión* del ADR-0004. Se **conserva** el
> resto: la tolerancia a drift de edad, el invariante "el face-match nunca auto-confirma", las bandas
> de umbral (<65 / 65-85 / >85 / 100), pgvector como verdad + FAISS como índice, y la compuerta de
> calidad.

## Decisión

**1. Motor de embedding: ArcFace, backbone IResNet100** (InsightFace).
- **Embedding de 512-d** (reemplaza los ~128-d de SFace). El campo de embedding se **versiona**
  (`model=arcface`, `version=iresnet100`) porque los vectores no son compatibles entre modelos
  (ADR-0007); migrar de modelo exige re-generar embeddings.
- **Detección + alineación**: detector de InsightFace (p. ej. RetinaFace/SCRFD) con landmarks para
  alinear antes del embedding. (Sustituye YuNet; YuNet queda como fallback ligero si hiciera falta.)
- **FAISS**: el índice HNSW pasa a **d=512**, métrica **coseno** (vectores normalizados). pgvector
  almacena vectores de 512-d.

**2. Scoring del MVP: solo-rostro.** La confianza del candidato la determina **únicamente** la
similitud facial (ajustada por drift). La **ubicación sigue siendo obligatoria** en el reporte como
contexto para el coordinador, pero **no entra al score** en el MVP (peso geo = 0; peso texto = 0). El
marco de **fusión multi-señal del ADR-0004 se conserva como diseño** para activarse post-MVP subiendo
los pesos; en el evento `match.evaluado` los pesos efectivos de geo/texto se reportan en 0.

**3. Umbrales a recalibrar para ArcFace.** El `τ0 ≈ 0.6` y los parámetros `α/β/Δ_max` del ADR-0004
eran de referencia para SFace; se **recalibran para ArcFace/IResNet100** en fase 04-testing
(ArcFace suele operar con umbrales de coseno distintos). Las **bandas de enrutamiento**
(<65 / 65-85 / >85 / 100) y el invariante de no auto-confirmación **no cambian**.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. ArcFace / IResNet100** ✅ | Precisión SOTA (clave para minimizar T2); embeddings 512-d robustos; ecosistema InsightFace maduro; on-prem (alinea ADR-0006) | Más pesado (GPU recomendada — ADR-0006 GPU on-prem); más dependencias que OpenCV; re-generar embeddings al migrar | Embeddings = biométrico (A04); el sesgo demográfico persiste (`ai-sec`) → mitigado por no auto-confirmación |
| **B. OpenCV SFace (~128-d)** (ADR-0004 original) | Ligero (CPU); menos deps | Precisión por debajo de SOTA → más falsos positivos/negativos en condiciones de desastre | Mayor riesgo de T2 con datos difíciles |
| **C. Fusión multi-señal completa en MVP** | Más robusto ante una foto mala | Complejidad de calibrar pesos geo/texto sin datos reales; alarga el MVP | Riesgo de mal calibrado temprano |
| **D. API gestionada (Rekognition)** | Cero ops | Biométricos a un tercero → contradice on-prem/ADR-0006/0008 | Exposición de biométricos (A04) — inaceptable |

> **B** queda como fallback si la GPU on-prem no está disponible (ArcFace en CPU es lento). **C** se
> activa post-MVP subiendo los pesos del marco de fusión ya diseñado.

## Consecuencias

- **Positivas:** mejor precisión donde más importa (reduce T2); embeddings de 512-d coherentes con el
  ejemplo de `reporte.creado` (ADR-0011); MVP más simple al scorear solo por rostro; el marco de
  fusión queda listo para activarse después.
- **Negativas / deuda asumida:** ArcFace **requiere GPU** para latencia aceptable (depende del equipo
  on-prem del ADR-0006); hay que **reescribir el adaptador** `opencv_facemapper.py` del
  `matching-worker` a ArcFace/InsightFace y **migrar el índice a 512-d**; **recalibrar** umbrales; el
  scoring solo-rostro **renuncia temporalmente** a la robustez de geo/texto ante una sola foto mala
  (mitigado: ubicación visible al coordinador + bandas que enrutan a revisión humana).
- **Impacto en threat model:**
  - **T2 (falso positivo):** mejor backbone baja la tasa base; el invariante de no auto-confirmación y
    el drift→coordinador se mantienen.
  - **A04/`ai-sec`:** embeddings de 512-d siguen siendo biométrico Restringido; el sesgo (pieles
    oscuras, menores) persiste y se contiene con revisión humana (sin cambio respecto a ADR-0004).
  - **T10 (merge erróneo):** sin señales geo/texto en el score, el coordinador es la salvaguarda
    principal en casos límite → reforzar la UI de match manual (ADR-0010).

## Decisiones abiertas

- `<TODO>` Recalibración de umbral coseno para ArcFace/IResNet100 y de `α/β/Δ_max` (fase 04-testing).
- ✅ **GPU MVP: RTX 3090 (24 GB)** on-prem, **compartida con el LLM** (ADR-0001). ArcFace IResNet100 usa ≈1-2 GB y deja inferencia rápida; bajo pico compite con el LLM por la GPU (mitiga la cola).
- `<TODO>` Detector concreto de InsightFace (RetinaFace vs SCRFD) y política de fallback a CPU/YuNet.
- `<TODO>` Plan de migración del índice y de los embeddings existentes (si los hubiera) a 512-d.
- `<TODO>` Reescritura del adaptador `opencv_facemapper.py` → `arcface_facemapper.py` y `config.py`.

## Disparadores de revisión

- La GPU on-prem no está disponible o no da abasto → fallback a SFace (B) o serving acelerado.
- Una sola foto mala produce demasiados falsos negativos → activar fusión multi-señal (C, post-MVP).
- Auditoría de sesgo revela disparidad inaceptable → recalibrar y reforzar revisión humana.
