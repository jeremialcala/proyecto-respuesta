# Despliegue — Respuesta

Artefactos de contenedores y orquestación (ADR-0014). Todas las apps son **container-ready**,
con **dev local en compose** y **manifiestos K8s para EKS/AWS**.

## Dev local (docker-compose)

```bash
cp .env.example .env                       # credenciales del bot de Meta (dev)
docker compose up -d --build               # base + ingestión + salida + core (sin perfiles)
docker compose --profile chat --profile gpu --profile llm up -d   # +chatbot, +matching-worker, +Ollama
```

Dependencias gestionadas que se emulan en local:
- **LocalStack** (`SQS/SNS/KMS`): crea al arrancar las colas (con DLQ por redrive) y topics del flujo
  (`deploy/localstack/init`, **idempotente**). Estado **efímero** (la persistencia de LocalStack es de
  pago) — ok para mensajería transitoria.
- **MinIO** (`S3`): bóveda de medios **persistente** en volumen (`minio-data`), así las fotos cifradas
  sobreviven a reinicios. `createbuckets` crea `respuesta-media`/`respuesta-quarantine` al arrancar.
- **Ollama** (perfil `llm`): LLM on-prem en GPU; reusa el volumen `ollama` del host (gemma3:27b +
  nomic-embed-text). El chatbot apunta a `OLLAMA_URL=http://llm:11434` (o `host.docker.internal`).

**Perfiles:** `chat` (chatbot-gateway), `gpu` (matching-worker, requiere NVIDIA Container Toolkit),
`llm` (Ollama empaquetado). Sin perfiles, esos tres no arrancan.

**Endpoints de boto3:** `AWS_ENDPOINT_URL=http://localstack:4566` (SQS/SNS/KMS) y, para los servicios
de bóveda (`vault-worker`, `matching-worker`), `AWS_ENDPOINT_URL_S3=http://minio:9000` (S3 → MinIO).
boto3 prioriza el endpoint específico de S3, así el código no cambia entre local y AWS.

> **Cifrado en dev:** el `vault-worker` usa `VAULT_CIPHER=passthrough` (guarda el JPEG plano, sin
> SSE-KMS) porque el `matching-worker` aún lee los bytes sin descifrar. **Producción** usa el envelope
> KMS de ADR-0008 (`VAULT_CIPHER=kms`, `S3_SSE=aws:kms`).

## Producción (EKS + kustomize)

```bash
# 1) Build & push a ECR (por app)
docker build -t $ECR/respuesta/webhook-gateway:0.1.0 apps/webhook-gateway && docker push $ECR/respuesta/webhook-gateway:0.1.0
docker build -t $ECR/respuesta/matching-worker:0.1.0 apps/matching-worker && docker push $ECR/respuesta/matching-worker:0.1.0

# 2) Sustituir ACCOUNT_ID / región / CERT_ID en deploy/k8s y aplicar
kubectl apply -k deploy/k8s
```

Requisitos del clúster (add-ons): **AWS Load Balancer Controller** (Ingress ALB), **KEDA** (escalado
por cola), **External Secrets Operator** (secretos desde Vault/Secrets Manager), **NVIDIA device
plugin** (nodos GPU). Cada workload usa **IRSA** con permisos mínimos.

**Planos GPU separados (ADR-0018):** el facematch **no comparte GPU con el LLM**. Cada uno corre en su
**pool GPU dedicado** vía `nodeSelector` + taint `respuesta.io/gpu-pool` (`facematch` vs `llm`) y
`podAntiAffinity` recíproca (defensa en profundidad: nunca co-residen en la misma máquina). El
`matching-worker` escala por profundidad de su cola con KEDA (mínimo **caliente** para latencia, máximo
para drenar olas); el LLM mantiene su propio dimensionamiento. **Prerrequisito de infra:** dos node
groups GPU (en EKS sa-east-1 y/o nodos on-prem) que porten esas etiquetas/taints — su IaC (eksctl/
Terraform) es parte del pendiente Gate 4.

**Plano de inferencia portable + burst (ADR-0019):** la extracción de embedding (GPU) se separa en una
**imagen OCI dedicada** (`apps/matching-worker/Dockerfile.inference`, **distinta** de la del worker),
stateless y **sin secretos**: consume `face.extract.requested`, devuelve `face.embedded` (**solo el
vector 512-d**; la galería/Vault/pgvector permanecen en-región). El worker in-region elige extractor por
config (`FACE_EXTRACTOR=local|remote`): en `remote` hace request-reply por el bus contra el plano de
inferencia, que puede correr en EKS sa-east-1, on-prem **o** vast.ai Secure Cloud (**destino =
configuración**). El **egress real a terceros está gated** por validación legal + PoC (decisiones
abiertas del ADR-0019). En modo `remote`, el matching-worker puede correr **CPU-only**.

| App | Tipo | Exposición | Escalado | Notas |
| :-- | :-- | :-- | :-- | :-- |
| webhook-gateway | HTTP sin estado | Ingress ALB (TLS ACM) | HPA (CPU) | publica `meta-received` |
| matching-worker | Worker por cola | — | KEDA (profundidad SQS) | pool GPU `facematch` dedicado (ADR-0018), ArcFace; idempotente por `event_id`; extractor local/remoto (ADR-0019) |
| inference-worker | Worker por cola (stateless) | — | KEDA (profundidad SQS) | imagen de inferencia portable (ADR-0019), pool GPU `facematch`, **sin secretos**, solo-vector |
| llm | Inferencia (Ollama) | ClusterIP | fijo (1) | pool GPU `llm` dedicado (ADR-0001/0018), no autoritativo |

Secretos esperados (creados por External Secrets, **no** versionados):
`webhook-gateway-secrets` (META_*), `matching-worker-secrets` (PGVECTOR_DSN, …).
