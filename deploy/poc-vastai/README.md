# PoC — plano de inferencia ArcFace en GPU on-demand (vast.ai) · ADR-0019

Kit para validar las **decisiones abiertas** de [ADR-0019](../../docs/00-project/adr/0019-imagen-inferencia-arcface-tensorrt-vastai.md)
con **datos sintéticos** antes de habilitar tráfico real o egress a terceros: cold-start, throughput,
latencia, egress e interrupción. Mide el contrato efímero `face.extract.requested` → `face.embedded`
(solo-vector) contra el `inference-worker` portable.

> **Regla dura (ADR-0019 §5/§6):** nunca PII real en el PoC. Usa `gen_synthetic_faces.py` o datos
> **consentidos**. Solo **vast.ai Secure Cloud / hosts verificados** (ISO 27001 / GDPR), preferentemente
> **región Brasil**; jamás el marketplace abierto. El egress real está **gated** por validación legal.

## Contenido

| Archivo | Qué es |
| :-- | :-- |
| `gen_synthetic_faces.py` | Genera caras sintéticas (sin PII) reproducibles. |
| `harness.py` | Publica trabajos, drena respuestas, calcula cold-start/throughput/latencia/egress. |
| `results-template.md` | Plantilla de resultados (dry-run vs vast.ai vs EKS) + veredicto. |
| `requirements.txt` | `boto3`, `pillow` (tooling del operador). |

```bash
pip install -r requirements.txt
python gen_synthetic_faces.py --count 200 --size 640 --out ./synthetic
```

## A) Dry-run local (valida el harness y el round-trip, en CPU)

Levanta el `inference-worker` contra LocalStack/MinIO (perfil `poc`). **No** da números de GPU
representativos (corre en CPU); valida wiring, contrato, correlación por `job_id` y las métricas.

```bash
# desde la raíz del repo
docker compose up -d localstack                              # crea colas/topics (init idempotente)
docker compose --profile poc up -d --build inference-worker  # imagen Dockerfile.inference, ARCFACE_USE_GPU=false
docker compose logs -f inference-worker                      # 1ª vez: descarga buffalo_l (~300 MB)

# harness desde el host (boto3 → LocalStack)
python harness.py \
  --endpoint http://localhost:4566 --region sa-east-1 \
  --extract-topic-arn arn:aws:sns:sa-east-1:000000000000:face-extract-requested \
  --reply-queue-url http://localhost:4566/000000000000/face-embedded-reply \
  --images ./synthetic --count 100 --concurrency 4 --timeout 180 --out results-dryrun.json
```

Esperado: `ok` ≈ `count`, `timeouts` 0, `cold_start_s` alto (carga del modelo en la 1ª), `detection_rate`
variable (las caras dibujadas no siempre se detectan — normal). Si todo casa, el harness está listo.

## C) Corrida local en GPU (sustituye a vast.ai)

Mismos imagen y bus que el dry-run, pero en la **GPU on-prem** (RTX 3090) y con **rostros detectables**
→ números reales de throughput/latencia/embedding **sin** salir a un tercero (sin el riesgo de egress
del §B). Requiere NVIDIA Container Toolkit. El override [`compose.gpu.yml`](compose.gpu.yml) activa la GPU.

```bash
# 1) dataset detectable (rostros reales FairFace/FFHQ o GAN sintético §6)
pip install -r requirements-prep.txt
python prep_dataset.py --source fairface --max 500 --size 512 --out ./faces

# 2) inference-worker en GPU (override) — desde la raíz del repo
docker compose up -d localstack
docker compose -f docker-compose.yml -f deploy/poc-vastai/compose.gpu.yml \
  --profile poc up -d --build inference-worker
docker compose logs -f inference-worker          # debe cargar el modelo en CUDA

# 3) harness
python harness.py \
  --endpoint http://localhost:4566 --region sa-east-1 \
  --extract-topic-arn arn:aws:sns:sa-east-1:000000000000:face-extract-requested \
  --reply-queue-url http://localhost:4566/000000000000/face-embedded-reply \
  --images ./faces --count 500 --concurrency 8 --timeout 300 --out results-local-gpu.json
```

Ahora **`detection_rate` y `avg_faces` deben ser >0** (rostros reales/GAN) → el embedding se ejercita de
verdad. `throughput_jobs_s`/`latency_*` son los de tu GPU. Vuelca el JSON en `results-template.md`
(columna "EKS sa-east-1 / on-prem"). Nota: el cold-start aquí **no** incluye aprovisionamiento ni pull
(la instancia ya corre y el modelo está cacheado); para esos, ver §B (vast.ai).

## B) Corrida real en vast.ai Secure Cloud (Brasil)

Config completa y scripts en **[`vast/`](vast/)** — runbook paso a paso en [`vast/README.md`](vast/README.md):
`aws-bootstrap.sh` (bus real sa-east-1), `iam-inference-policy.json` (IAM mínimo del nodo),
`env.vast.example`, `launch.sh`/`onstart.sh`/`teardown.sh` (vastai CLI, **login ECR de corta vida**,
**interruptible**, Brasil verificado). Dataset detectable con `prep_dataset.py` (FairFace/FFHQ reales o
**GAN sintético** §6 — `pip install -r requirements-prep.txt`). Resumen:

```bash
AWS_REGION=sa-east-1 bash vast/aws-bootstrap.sh                 # crea topics/colas reales
python prep_dataset.py --source fairface --max 500 --out ./faces
ECR_ACCOUNT=<acct> TAG=0.1.0 BID=0.12 ASK_ID=<id> bash vast/launch.sh   # nodo interruptible
python harness.py --region sa-east-1 \
  --extract-topic-arn arn:aws:sns:sa-east-1:<acct>:face-extract-requested \
  --reply-queue-url https://sqs.sa-east-1.amazonaws.com/<acct>/face-embedded-reply \
  --images ./faces --count 1000 --concurrency 16 --timeout 300 --out results-vastai.json
bash vast/teardown.sh <instance_id>                            # minimización (§B.4)
```

Con rostros reales/GAN, `detection_rate`/`avg_faces` ya salen >0 (mide el embedding). Interruptible →
mide la tasa de interrupción; el redrive idempotente (ADR-0018, `event_id`) reabsorbe los `timeouts`.

## Modelo de costo (orientativo, feasibility §4.2–4.3)

Ola de ~50k fotos + ~5k clips ≈ **~3 GPU-hora**; en 10 GPUs ≈ **~18 min** de wall-clock.
vast.ai Secure Cloud ≈ **$1.5–3 / ola**; AWS sa-east-1 (g5) ≈ **2–4×**. El valor es **elasticidad y
aislamiento**, no el costo de cómputo (marginal).

## Qué NO cubre este PoC

Baking real del engine **TensorRT** (requiere GPU+modelo en build), **validación legal** de residencia y
registro de sub-procesador, **disparador del burst** (KEDA → API de aprovisionamiento de vast.ai) y el
lifecycle de la cola de respuesta por pod. Son decisiones abiertas de [ADR-0019](../../docs/00-project/adr/0019-imagen-inferencia-arcface-tensorrt-vastai.md).
