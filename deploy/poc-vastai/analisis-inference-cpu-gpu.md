# Análisis: cómo procesa el `inference-worker` (CPU vs GPU) — ADR-0019

Análisis del plano de inferencia ([`inference_main`](../../apps/matching-worker/src/matching_worker/inference_main.py))
en modo **solo-CPU**, con la corrida en **GPU (RTX 3090 local)** como contraste. Incluye un hallazgo
importante: hasta este análisis, el worker corría ArcFace **en CPU aunque se pidiera GPU**, por un
conflicto de dependencias (ver §5).

Fecha de medición: 2026-06-28. Equipo: 12 vCPU / 15 GiB (contenedor) · NVIDIA RTX 3090 24 GB (driver 591.86).

---

## 1. Qué hace el proceso

El `inference-worker` es **stateless**: consume `face.extract.requested`, corre el pipeline ArcFace y
publica `face.embedded` con **solo los vectores 512-d** (minimización A04 — ADR-0019 §4). No toca
Postgres, Vault ni S3.

Composición ([`inference_main.main()`](../../apps/matching-worker/src/matching_worker/inference_main.py)):

```
InferenceConfig.from_env()                         # 12-factor: región, colas, ARCFACE_USE_GPU…
  → ArcFaceMapper(model_root, ArcFaceParams)       # InsightFace buffalo_l (detector SCRFD + ArcFace)
  → SnsEventBus({"face.embedded": <ARN>})          # publica solo-vector
  → InferenceService(mapper, bus)                  # caso de uso puro (sin infra)
  → SqsConsumer(extract_queue, …, on_extract_requested).start()   # bucle long-poll
```

## 2. Flujo de un mensaje (paso a paso)

1. **Recepción** — [`SqsConsumer.start()`](../../apps/matching-worker/src/matching_worker/adapters/sqs_consumer.py)
   hace `receive_message` con long polling (`WaitTimeSeconds=20`, hasta 10 por lote). Entrega
   *at-least-once*.
2. **Decodificación** — [`InferenceService.on_extract_requested`](../../apps/matching-worker/src/matching_worker/application/inference_service.py)
   valida `job_id`/`image_b64` y hace `base64.b64decode`.
3. **Inferencia** — [`ArcFaceMapper.map_image`](../../apps/matching-worker/src/matching_worker/adapters/arcface_facemapper.py):
   `cv2.imdecode` (CPU) → `app.get(arr)` = **detección SCRFD + alineación por landmarks + embedding
   ArcFace/IResNet100 (512-d normalizado)**. Filtra rostros menores a `min_size_px` (80px).
4. **Publicación** — `bus.publish("face.embedded", {job_id, faces:[vector+geometría]})`. **Ninguna
   imagen vuelve ni se persiste.**
5. **Confirmación** — si el handler no lanzó, `delete_message`. Si lanzó, **no se borra** → redrive a
   DLQ tras `maxReceiveCount` (idempotencia por `event_id`, ADR-0011/0012).

## 3. El modo "solo CPU"

El destino de cómputo es **configuración, no código**. En
[`ArcFaceMapper._ensure_loaded`](../../apps/matching-worker/src/matching_worker/adapters/arcface_facemapper.py):

```python
providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
             if self._p.use_gpu else ["CPUExecutionProvider"])
app = FaceAnalysis(name="buffalo_l", root=self._model_root, providers=providers)
app.prepare(ctx_id=0 if self._p.use_gpu else -1)
```

- `ARCFACE_USE_GPU=false` → **solo** `CPUExecutionProvider`, `ctx_id=-1`. onnxruntime ejecuta los ONNX
  (SCRFD + ArcFace) sobre CPU multihilo.
- **Carga perezosa**: `FaceAnalysis` se instancia en la **primera** imagen (no al arrancar). Esa primera
  inferencia incluye la carga del modelo desde `/models/insightface` (buffalo_l, ~300 MB cacheado en un
  volumen). De ahí el "cold-start" alto en la primera respuesta.
- Es el modo del **dry-run del PoC** (perfil `poc` del compose): valida wiring, contrato y métricas; no
  da números representativos de GPU.

## 4. Concurrencia y escalado (clave)

El consumidor es **un único bucle secuencial**: procesa los mensajes de un lote **uno a uno** en el hilo
principal. No hay paralelismo interno. Por tanto:

- La **concurrencia del harness no acelera el cómputo**: si se publican 4 jobs a la vez, el worker los
  atiende en serie; la concurrencia solo llena la cola y se refleja como **encolado** en la latencia
  p50/p95.
- El throughput de un worker ≈ `1 / (tiempo de pipeline por imagen)`.
- Para escalar se replican **procesos/pods** (uno por GPU/núcleos), con **KEDA por profundidad de cola**
  (ADR-0018) — no subiendo hilos dentro del worker. La idempotencia + DLQ permiten N consumidores sobre
  la misma cola sin doble efecto.

## 5. Hallazgo: el worker corría en CPU aunque se pidiera GPU

Durante este análisis se detectó que la imagen `Dockerfile.inference` tenía **dos** paquetes onnxruntime
instalados:

```
onnxruntime 1.23.2  +  onnxruntime-gpu 1.23.2   →  get_available_providers() = ['Azure','CPU']  (sin CUDA)
```

Causa: `insightface` declara `onnxruntime` (CPU) como dependencia; al instalarse junto a
`onnxruntime-gpu` **comparten el paquete `onnxruntime/`** y el de CPU pisa al de GPU. Resultado: aunque
`ARCFACE_USE_GPU=true` pida `CUDAExecutionProvider`, **no existe** y onnxruntime **cae a CPU en
silencio**. Esto invalidó retroactivamente las corridas "GPU" en vast.ai (eran CPU + overhead de túnel).

Segundo problema acoplado: el `onnxruntime-gpu` actual (≥1.19) necesita **cuDNN 9**, pero la base era
`cuda:12.2.2-cudnn8` → aun resolviendo el conflicto, el provider CUDA no cargaría.

**Fix aplicado** ([`Dockerfile.inference`](../../apps/matching-worker/Dockerfile.inference)):
- Base → `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` (cuDNN 9).
- Tras `pip install .`: `pip uninstall -y onnxruntime onnxruntime-gpu` y reinstalar **solo**
  `onnxruntime-gpu`, con un **assert en build** de que `CUDAExecutionProvider` está disponible.

Verificación en runtime (RTX 3090): `Applied providers: ['CUDAExecutionProvider', 'CPUExecutionProvider']`.

## 6. Medición: CPU vs GPU

Mismo dataset (250 rostros **FFHQ reales** a 256px), 120 jobs, concurrency 4, **local sin túnel**
(LocalStack como bus). Archivos: [`results-cpu-ffhq.json`](results-cpu-ffhq.json),
[`results-gpu-3090-ffhq.json`](results-gpu-3090-ffhq.json).

| Métrica            | CPU (12 vCPU) | GPU (RTX 3090) | Mejora |
| :----------------- | :-----------: | :------------: | :----: |
| throughput (jobs/s)|     2.19      |    **6.23**    | ~2.8×  |
| latency p50 (s)    |     1.375     |    **0.625**   | ~2.2×  |
| latency p95 (s)    |     1.703     |    **0.72**    | ~2.4×  |
| wall 120 img (s)   |     54.7      |    **19.3**    | ~2.8×  |
| detection_rate     |      1.0      |      1.0       |   =    |
| ok / timeouts      |    120 / 0    |    120 / 0     |   =    |

Notas:
- La ganancia (~2.8×) es **moderada**, no 10×, porque buffalo_l es ligero y a 256px una parte del tiempo
  es decodificación/pre-proceso en CPU + overhead por-imagen. Con imágenes mayores o procesamiento por
  lotes la GPU se separa más.
- El **cold-start** no aparece aquí (modelo pre-cargado en el warmup). En frío, la primera inferencia
  suma la carga de buffalo_l.
- **No comparable** con los números de vast.ai de hoy: aquellos iban por túnel cloudflare (RTT ~10 s
  dominante) y, además, en CPU (§5).

## 7. Implicaciones para ADR-0019

- **CPU** sirve para el dry-run/validación de contrato y para volúmenes bajos; **GPU** es el modo de
  producción/burst. El destino es configuración (`ARCFACE_USE_GPU`), no código — confirmado.
- La imagen **ya es GPU-real** tras el fix; reconstruir y re-publicar (ECR/registry) antes de cualquier
  medición de burst que pretenda números de GPU.
- El **escalado elástico** es por réplicas + KEDA por cola (ADR-0018), no por hilos. Idempotencia + DLQ
  sostienen N consumidores e interrupciones (ADR-0012).
- **Riesgo operativo nuevo** (observado en la PoC): los hosts del marketplace verificado de vast.ai
  fueron poco fiables (5/6 no-Brasil se atascaron en `loading`); el `loading`/pull de una imagen ~3 GB
  cross-continente es un cuello real. Mitigaciones: registry con CDN/cercanía a los hosts, imagen más
  delgada, y baking del engine TensorRT (decisión abierta del ADR) para bajar cold-start.

## 8. Limitaciones de esta medición

- Dataset a 256px (FFHQ mirror) — egress y pre-proceso menores que con fotos grandes reales.
- Worker único (sin medir escalado horizontal); throughput agregado escalaría ~linealmente con réplicas.
- `map_video` no implementado (solo `map_image`); el costo de video (tracking/windowing) no está medido.
- Métrica `cold_start_s` del harness = mínimo de latencias (job más rápido), no necesariamente la
  primera carga del modelo.
