# Resultados PoC — DRY-RUN local (CPU) · ADR-0019

> Corrida de **validación del harness y el round-trip** (NO números de GPU). Generada con
> `harness.py` contra el `inference-worker` (perfil `poc`) sobre LocalStack/MinIO, en CPU.

## Metadatos

| Campo | Valor |
| :-- | :-- |
| Fecha | 2026-06-28 |
| Destino | dry-run local (CPU) — LocalStack `sa-east-1` |
| Imagen | `respuesta/matching-worker-inference` (`Dockerfile.inference`, `ARCFACE_USE_GPU=false`) |
| Dataset | sintético (`gen_synthetic_faces.py`, caras dibujadas, 640×640) |
| Parámetros | `--count 100 --concurrency 8 --timeout 120` |

## Métricas (`results-dryrun.json`)

| Métrica | Dry-run local (CPU) | Notas |
| :-- | :--: | :-- |
| ok / count | **100 / 100** | round-trip SQS/SNS + correlación por `job_id` correctos |
| timeouts | **0** | sin pérdidas; idempotencia/redrive no se gatilló |
| cold_start_s | 0.20 | modelo **ya cacheado** (volumen `insightface-models` compartido) → no mide descarga real |
| throughput_jobs_s | **8.34** | CPU, consumidor único; en GPU sube mucho (feasibility: ~50–150 img/s) |
| latency p50 / p95 / p99 (s) | 0.92 / 1.11 / 1.13 | round-trip completo (incluye hop LocalStack) |
| **detection_rate** | **0.0** | ⚠️ SCRFD no detecta las caras **dibujadas** → la etapa de embedding no se ejercita |
| avg_faces | 0 | idem |
| egress_mb_sent | 10.81 | 100 imágenes 640×640 JPEG (~108 KB c/u) |
| wall_s | 11.98 | |

## Lectura

- ✅ **Validado:** wiring del plano de inferencia, contrato efímero (`face.extract.requested` →
  `face.embedded` solo-vector), correlación por `job_id`, métricas del harness, y resiliencia básica
  (0 timeouts). La imagen `Dockerfile.inference` arranca y consume en CPU.
- ⚠️ **No representativo:** (1) cold-start real (el modelo estaba cacheado), (2) throughput/latencia de
  GPU, (3) **embedding** (las caras dibujadas no las detecta SCRFD → `detection_rate=0`).
- ➡️ **Para números de embedding y de GPU:** repetir en GPU real con caras **GAN/consentidas** (ADR-0019
  §6) siguiendo el runbook (`README.md` §B). El `egress_mb_sent` ya orienta la minimización (pre-recorte).

## Pendiente (decisiones abiertas ADR-0019)

Baking TensorRT, ejecución en vast.ai Secure Cloud (Brasil), validación legal del egress, disparador
del burst (KEDA→API), tokens de corta vida. Ver `results-template.md` para la corrida real.
