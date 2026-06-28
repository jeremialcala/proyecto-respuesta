# Corrida real en vast.ai — config (ADR-0019)

Configuración para ejecutar el `inference-worker` en **vast.ai Secure Cloud**, **interruptible**, región
**Brasil**, imagen privada en **ECR sa-east-1**. Mide cold-start, throughput, latencia, egress e
**interrupción** contra el bus real. Complementa el [README del PoC](../README.md) (dry-run local).

> **Gobernanza (ADR-0019 §5/§6).** El egress de **biometría real** (FFHQ/FairFace) a un sub-procesador
> de terceros requiere tu **validación legal** previa y registro de vast.ai+DC como sub-procesador. Para
> un PoC puramente técnico sin ese riesgo, usa caras **GAN sintéticas** (`prep_dataset.py --source gan`).
> Solo **Secure Cloud / hosts verificados** (ISO 27001 / GDPR), nunca el marketplace abierto.

## Archivos

| Archivo | Qué hace |
| :-- | :-- |
| `aws-bootstrap.sh` | Crea en AWS real sa-east-1 los topics/colas (`face-extract-requested`, `face-embedded`, `face-embedded-reply`) con suscripción raw. Idempotente. |
| `iam-inference-policy.json` | IAM de **alcance mínimo** del nodo (solo SQS receive/delete + SNS publish). Sin Vault/KMS/S3/ECR en runtime. |
| `env.vast.example` | Plantilla de env del nodo (→ copia a `env.vast`). Recomendado STS de corta vida. |
| `launch.sh` | Busca ofertas verificadas/Brasil/interruptible y crea la instancia con **login ECR de corta vida** + env + onstart. |
| `onstart.sh` | Arranque del worker en el nodo (`python3 -m matching_worker.inference_main`). |
| `teardown.sh` | Destruye la instancia (minimización: vast.ai elimina los datos del nodo). |

## Pasos

### 1. Recursos del bus (una vez, con creds admin)
```bash
AWS_REGION=sa-east-1 bash vast/aws-bootstrap.sh   # imprime SQS_*/SNS_* — guárdalos
```

### 2. Credenciales mínimas del nodo (sin secretos a Vault, §4)
```bash
sed "s/<ACCOUNT_ID>/$(aws sts get-caller-identity --query Account --output text)/g" \
  vast/iam-inference-policy.json > /tmp/pol.json
# Crea un usuario/rol con esa política y EMITE credenciales de corta vida (recomendado STS):
aws sts get-session-token --duration-seconds 7200   # → AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN
cp vast/env.vast.example vast/env.vast && $EDITOR vast/env.vast   # pega creds + SQS_*/SNS_*
```

### 3. Imagen de inferencia en ECR (host con CUDA para construir)
```bash
aws ecr create-repository --repository-name respuesta/matching-worker-inference --region sa-east-1 || true
aws ecr get-login-password --region sa-east-1 | docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.sa-east-1.amazonaws.com
docker build -f apps/matching-worker/Dockerfile.inference \
  -t <ACCOUNT_ID>.dkr.ecr.sa-east-1.amazonaws.com/respuesta/matching-worker-inference:0.1.0 \
  apps/matching-worker
docker push <ACCOUNT_ID>.dkr.ecr.sa-east-1.amazonaws.com/respuesta/matching-worker-inference:0.1.0
```
> El **engine TensorRT pre-horneado** (decisión abierta del ADR) baja el cold-start; mientras tanto la
> base InsightFace/ONNX-GPU es portable y mide el camino completo.

### 4. Dataset (rostros detectables)
```bash
pip install -r requirements-prep.txt
# FairFace (real, fácil vía HF) — o FFHQ local — o GAN sintético (recomendado §6):
python prep_dataset.py --source fairface --max 500 --size 512 --out ./faces
# python prep_dataset.py --source dir --src /ruta/ffhq-subset --max 500 --size 512 --out ./faces
```

### 5. Lanzar el nodo interruptible
```bash
ECR_ACCOUNT=<ACCOUNT_ID> TAG=0.1.0 BID=0.12 bash vast/launch.sh            # lista ofertas
ECR_ACCOUNT=<ACCOUNT_ID> TAG=0.1.0 BID=0.12 ASK_ID=<id> bash vast/launch.sh # crea
vastai logs <instance_id>   # espera "escuchando face.extract.requested" (1ª vez baja el modelo)
```

### 6. Medir (harness desde en-región o tu equipo)
```bash
python harness.py --region sa-east-1 \
  --extract-topic-arn arn:aws:sns:sa-east-1:<ACCOUNT_ID>:face-extract-requested \
  --reply-queue-url https://sqs.sa-east-1.amazonaws.com/<ACCOUNT_ID>/face-embedded-reply \
  --images ./faces --count 1000 --concurrency 16 --timeout 300 --out results-vastai.json
```
- **Cold-start real:** primera corrida con el nodo recién creado (incluye pull + carga de modelo).
- **Interrupción:** al ser interruptible, el host puede reclamar la GPU → verás `timeouts`; el redrive
  idempotente (ADR-0018, `event_id`) los reabsorbe sin doble efecto. Corre una ventana larga para medir
  la tasa. **detection_rate** y **avg_faces** ahora deberían ser >0 (rostros reales/GAN).
- **Egress:** `egress_mb_sent` del JSON → evalúa pre-recortar la cara en-región.

### 7. Cierre (minimización, §B.4)
```bash
bash vast/teardown.sh <instance_id>   # destruye la instancia y sus datos
# revoca las credenciales STS/usuario del nodo; vuelca results-vastai.json en ../results-template.md
```

## Notas

- `vastai` cambia de sintaxis entre versiones — verifica con `vastai search offers --help` y
  `vastai create instance --help` (los flags `--bid`, `--login`, `--env`, `--onstart-cmd`).
- Interruptible factura por puja; sube `BID` si te reclaman demasiado. Para los números **base** sin
  reclamos, repite con una instancia **on-demand** (sin `--bid`).
- El nodo nunca toca Vault/galería/pgvector: solo `imagen→vector` por el bus (ADR-0019 §4).
