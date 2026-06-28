# Resultados PoC — plano de inferencia ArcFace (ADR-0019)

> Rellenar tras cada corrida. Objetivo: validar las **decisiones abiertas** de ADR-0019 con **datos
> sintéticos/consentidos** (nunca PII real, §6) antes de habilitar tráfico real / egress a terceros.

## Metadatos de la corrida

| Campo | Valor |
| :-- | :-- |
| Fecha | |
| Destino | dry-run local (CPU) / vast.ai Secure Cloud (Brasil) / EKS sa-east-1 (g5) |
| GPU / instancia | (p. ej. RTX 4090 on-demand, reliability, DC, host verificado) |
| Imagen | `respuesta/matching-worker-inference:<tag>` (digest) |
| Dataset | sintético (`gen_synthetic_faces.py`, seed/size) / consentido |
| Parámetros harness | `--count … --concurrency … --timeout …` |

## Métricas (de `results.json` + cronómetro de aprovisionamiento)

| Métrica | Dry-run local (CPU) | vast.ai Secure Cloud | EKS sa-east-1 (base) | Notas |
| :-- | :--: | :--: | :--: | :-- |
| **Aprovisionamiento** (provision→listo) | n/a | | | solo real; cronometrar fuera del harness |
| **Pull de imagen** | n/a | | | tamaño imagen CUDA/TensorRT |
| **Cold-start** (`cold_start_s`, 1ª resp ≈ carga modelo) | | | | engine pre-horneado debería bajarlo |
| **Throughput** (`throughput_jobs_s`) | | | | feasibility estima ~50–150 img/s en GPU |
| **Latencia p50 / p95 / p99** (s) | | | | round-trip incluye egress+ingress |
| **Tasa de detección** (`detection_rate`) | | | | baja con caras dibujadas; alta con GAN/consentidas |
| **Timeouts / errores** | | | | resiliencia (A08, idempotencia ADR-0018) |
| **Egress enviado** (`egress_mb_sent`) | | | | minimización: enviar la cara recortada, no la foto |
| **Tasa de interrupción** | n/a | | n/a | solo `interruptible`; medir en ventana larga |
| **Costo / ola** (USD) | n/a | | | ~$1.5–3 vast.ai vs 2–4× AWS (feasibility §4.3) |

## Veredicto

- [ ] Cold-start dentro del SLO de la primera respuesta tras inactividad.
- [ ] Throughput suficiente para drenar la ola objetivo dentro del SLO de cola.
- [ ] Egress/latencia aceptables (¿se justifica pre-recorte en-región?).
- [ ] Interrupción tolerable con idempotencia + redrive (ADR-0018) — o reservar on-demand para lo sensible.
- [ ] **Validación legal** de residencia para egress efímero fuera de São Paulo: ☐ aprobada ☐ pendiente.

**Decisión:** (consolidar base en-región / habilitar burst a vast.ai / conmutar a EKS sa-east-1 — opción C)

## Disparadores de revisión observados (ADR-0019)

- (anotar si la tasa de interrupción o el cold-start degradan el SLO; si el costo del burst supera ampliar
  la base; si vast.ai cambia su Secure Cloud / presencia en Brasil.)
