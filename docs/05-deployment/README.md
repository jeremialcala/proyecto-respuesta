# Fase 05 — Deployment

CI/CD con 7 gates de seguridad (SAST, SCA, secrets, license, container, IaC, DAST), IaC endurecido
(Modelo A, hosting São Paulo sa-east-1 — ADR-0003/ADR-0006), estrategias de release y runbook de rollback.

**Gate 4 (cierre):** pipeline limpio + IaC escaneado + runbook de rollback.

## Artefactos disponibles (ADR-0014)

Contenedores y orquestación implementados en `deploy/` y por app:

- **Imágenes OCI** no-root por servicio: `apps/webhook-gateway/Dockerfile` (python-slim) y
  `apps/matching-worker/Dockerfile` (base CUDA para ArcFace/GPU).
- **Dev local**: `docker-compose.yml` (Postgres+pgvector, Redis, LocalStack SQS/SNS/KMS, **MinIO**
  como bóveda S3 persistente, Ollama y servicios; perfiles `chat`/`gpu`/`llm`) + init de colas/topics
  con DLQ por redrive (idempotente).
- **EKS/AWS**: `deploy/k8s/` (kustomize) con IRSA por workload, Ingress ALB + HPA (gateway), KEDA por
  profundidad de cola + nodos GPU (matching), Pod Security restricted y secretos vía External Secrets.
- **Planos GPU separados (ADR-0018)**: el facematch corre en un **pool GPU dedicado** (`nodeSelector` +
  taint `respuesta.io/gpu-pool=facematch`) distinto del pool del LLM, con `podAntiAffinity` recíproca,
  para que ninguna ola de matching degrade la latencia conversacional y cada carga escale por su métrica.

Ver [ADR-0014](../00-project/adr/0014-contenedores-despliegue-eks.md) y `deploy/README.md`.

**Pendiente Gate 4:** IaC del clúster (Terraform/eksctl), escaneo+firma de imágenes (cosign) y el
pipeline CI/CD (build → test → push ECR → `kubectl apply -k`).
