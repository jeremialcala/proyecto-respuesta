# Despliegue — Respuesta

Artefactos de contenedores y orquestación (ADR-0014). Todas las apps son **container-ready**,
con **dev local en compose** y **manifiestos K8s para EKS/AWS**.

## Dev local (docker-compose)

```bash
cp .env.example .env            # credenciales del bot de Meta (dev)
docker compose up --build       # postgres+pgvector, redis, localstack (SQS/SNS) y webhook-gateway
docker compose --profile gpu up # añade matching-worker (requiere NVIDIA Container Toolkit)
```

LocalStack crea al arrancar las colas (con DLQ por redrive) y topics del flujo (`deploy/localstack/init`).
boto3 usa `AWS_ENDPOINT_URL=http://localstack:4566`, así que el código no cambia entre local y AWS.

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
