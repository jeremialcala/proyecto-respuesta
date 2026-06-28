# Corrida local + GPU on-demand en vast.ai (bus por túnel) — ADR-0019

Variante de la [corrida en vast.ai](README.md) pensada para **tu configuración local**: el bus de mensajes
es **tu LocalStack** (docker-compose) expuesto por un **túnel**, y solo el **cómputo GPU** se va a una
instancia **on-demand** de vast.ai. No se levanta SQS/SNS real en AWS; ECR se usa **solo** para que el
nodo haga *pull* de la imagen de inferencia.

```
[tu PC / Docker]                                   [vast.ai · GPU on-demand]
  LocalStack (bus SQS/SNS) ──┐                        inference-worker (CUDA)
  harness.py (lee ./faces,   │  cloudflared (https)     · consume face-extract-requested
   publica face-extract,     └────────────────────▶    · ArcFace en GPU
   drena face-embedded-reply)◀──────────────────────   · publica face-embedded
```

El harness local hace de **worker in-region** (lee el dataset y despacha); la GPU remota solo hace
imagen→vector vía el bus tuneleado. El round-trip atraviesa: harness → SNS `face-extract-requested`
(LocalStack) → SQS `face-extract-requested` → **[túnel]** → nodo vast.ai → **[túnel]** → SNS
`face-embedded` (LocalStack) → SQS `face-embedded-reply` → harness.

> **Gobernanza (ADR-0019 §5/§6).** Con dataset **FairFace/FFHQ real** hay **egress de biometría real a un
> tercero** (vast.ai): requiere tu **validación legal previa** y registro de vast.ai+DC como
> sub-procesador. Para un PoC puramente técnico, usa caras **GAN** (`prep_dataset.py --source gan`). Solo
> **Secure Cloud / hosts verificados** (ISO 27001 / GDPR). El túnel abre tu bus al exterior **solo**
> mientras corre: ciérralo al terminar.

## Archivos (esta variante)

| Archivo | Qué hace |
| :-- | :-- |
| `tunnel.sh` | Expone LocalStack:4566 por cloudflared (o ngrok). Imprime la URL pública. |
| `env.vast.local.example` | Env del nodo: creds **dummy** (bus = LocalStack), imagen en ECR. → copia a `env.vast.local`. |
| `launch-ondemand.sh` | Crea la instancia **on-demand** (sin `--bid`), login ECR de corta vida, inyecta el bus tuneleado. |
| `teardown.sh` | Destruye la instancia (minimización). Reutilizado de la variante AWS. |

## Prerrequisitos

- `vastai` CLI autenticada: `vastai set api-key <API_KEY>`.
- `aws` CLI con permiso `ecr:GetAuthorizationToken` (solo para el pull de la imagen).
- `cloudflared` instalado (`winget install --id Cloudflare.cloudflared`) — o `ngrok` con authtoken.
- Docker Desktop (para construir/empujar la imagen; **no** necesita GPU: instala el wheel `onnxruntime-gpu`).
- Dataset detectable en `./faces` (paso 2).

## Pasos

### 1. Imagen de inferencia en ECR (una vez por TAG)
```bash
aws ecr create-repository --repository-name respuesta/matching-worker-inference --region sa-east-1 || true
aws ecr get-login-password --region sa-east-1 | docker login --username AWS --password-stdin \
  <ECR_ACCOUNT>.dkr.ecr.sa-east-1.amazonaws.com
docker build -f apps/matching-worker/Dockerfile.inference \
  -t <ECR_ACCOUNT>.dkr.ecr.sa-east-1.amazonaws.com/respuesta/matching-worker-inference:0.1.0 \
  apps/matching-worker
docker push <ECR_ACCOUNT>.dkr.ecr.sa-east-1.amazonaws.com/respuesta/matching-worker-inference:0.1.0
```

### 2. Dataset detectable
```bash
cd deploy/poc-vastai
pip install -r requirements-prep.txt
python prep_dataset.py --source fairface --max 500 --size 512 --out ./faces   # real (ver gobernanza)
# o, sin riesgo de egress real:
# python prep_dataset.py --source gan --max 500 --size 512 --out ./faces
```

### 3. Bus local arriba (LocalStack)
```bash
# desde la raíz del repo
docker compose up -d localstack     # init crea face-extract-requested / face-embedded / face-embedded-reply
curl -s http://localhost:4566/_localstack/health   # sanity
```
> No levantes `inference-worker` local: en esta variante la inferencia corre en vast.ai.

### 4. Túnel (deja esta terminal abierta)
```bash
bash deploy/poc-vastai/vast/tunnel.sh
# copia la URL https://<...>.trycloudflare.com  → es tu TUNNEL_URL
```

### 5. Lanzar el nodo on-demand
```bash
cp deploy/poc-vastai/vast/env.vast.local.example deploy/poc-vastai/vast/env.vast.local   # (una vez)
cd deploy/poc-vastai/vast
ECR_ACCOUNT=<ECR_ACCOUNT> TAG=0.1.0 TUNNEL_URL=https://<...>.trycloudflare.com bash launch-ondemand.sh
ECR_ACCOUNT=<ECR_ACCOUNT> TAG=0.1.0 TUNNEL_URL=https://<...>.trycloudflare.com ASK_ID=<id> \
  bash launch-ondemand.sh
vastai logs <instance_id>   # espera la carga del modelo (1ª vez baja buffalo_l ~300 MB)
```

### 6. Medir (harness desde tu PC → LocalStack local)
```bash
cd deploy/poc-vastai
python harness.py \
  --endpoint http://localhost:4566 --region sa-east-1 \
  --extract-topic-arn arn:aws:sns:sa-east-1:000000000000:face-extract-requested \
  --reply-queue-url http://localhost:4566/000000000000/face-embedded-reply \
  --images ./faces --count 500 --concurrency 8 --timeout 300 --out results-vastai-local.json
```
- El harness habla con **LocalStack local** (no con el túnel): el túnel es solo para que el **nodo** alcance el bus.
- **Cold-start real:** primera corrida con el nodo recién creado (incluye pull + carga del modelo en GPU).
- **detection_rate / avg_faces > 0** con rostros reales/GAN → mide el embedding de verdad.
- **Egress:** `egress_mb_sent` del JSON → evalúa pre-recortar la cara en-región.
- Vuelca el JSON en [`../results-template.md`](../results-template.md).

### 7. Cierre (minimización, §B.4)
```bash
bash deploy/poc-vastai/vast/teardown.sh <instance_id>   # destruye la instancia y sus datos
# Ctrl-C en la terminal del túnel para cerrarlo.
```

## Notas y resolución de problemas

- **boto3 y el endpoint:** el nodo recibe `AWS_ENDPOINT_URL=<túnel>`; boto3 lo prioriza sobre el host de
  `SQS_EXTRACT_QUEUE_URL`, así que las llamadas SQS/SNS van al túnel aunque la URL lleve otro host. El
  ARN de SNS lo resuelve LocalStack por nombre/cuenta (`000000000000`).
- **El host del túnel cambia** en cada arranque de cloudflared → vuelve a pasar `TUNNEL_URL` al relanzar.
- **Long polling:** el worker usa `WaitTimeSeconds`=20; cloudflared sostiene esa conexión sin problema.
- **`timeouts` altos / sin respuestas:** confirma que (a) el túnel sigue arriba, (b) `vastai logs`
  muestra "inference-worker arriba", (c) no cerraste LocalStack. Reintenta el harness: el consumo es
  idempotente (ADR-0018, `event_id`).
- **On-demand vs interruptible:** esta variante usa on-demand (no la reclaman). Para medir interrupción,
  usa la variante AWS con `launch.sh` (`--bid`).
- El nodo nunca toca Vault/galería/pgvector: solo `imagen→vector` por el bus (ADR-0019 §4).
