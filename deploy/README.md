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

| App | Tipo | Exposición | Escalado | Notas |
| :-- | :-- | :-- | :-- | :-- |
| webhook-gateway | HTTP sin estado | Ingress ALB (TLS ACM) | HPA (CPU) | publica `meta-received` |
| matching-worker | Worker por cola | — | KEDA (profundidad SQS) | GPU (`nvidia.com/gpu`), ArcFace |

Secretos esperados (creados por External Secrets, **no** versionados):
`webhook-gateway-secrets` (META_*), `matching-worker-secrets` (PGVECTOR_DSN, …).
