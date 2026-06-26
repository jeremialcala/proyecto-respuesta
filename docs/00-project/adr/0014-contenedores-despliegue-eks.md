# ADR-0014: Contenedores OCI y despliegue en AWS (EKS + kustomize, compose local)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 05-deployment
- **Controles OWASP afectados:** A01 (acceso/IRSA), A02 (misconfiguration/hardening), A05 (config), A08
- **Relacionado:** [ADR-0006](0006-residencia-sao-paulo.md) (AWS sa-east-1), [ADR-0012](0012-broker-aws-sqs-sns.md) (SQS/SNS), [ADR-0008](0008-boveda-llaves-identidad.md) (Vault/secretos), [ADR-0013](0013-arcface-scoring-solo-rostro.md) (GPU)

## Contexto

Todas las apps deben ser **container-ready** (imagen OCI reproducible), tener un entorno **local
equivalente** (compose) y manifiestos listos para **Kubernetes en AWS**. El sistema mezcla servicios
HTTP sin estado (webhook-gateway) y workers dirigidos por cola (matching-worker, y los próximos Meta
Handler / Worker de Bóveda), uno de ellos **GPU-bound** (ArcFace, ADR-0013). La residencia es AWS
`sa-east-1` (ADR-0006) y el bus es SQS/SNS (ADR-0012).

## Decisión

**1. Imágenes OCI por app (multi-stage, no-root).** `Dockerfile` por servicio:
- **webhook-gateway**: base `python:3.11-slim`, build → runtime, usuario `10001`, `HEALTHCHECK`,
  `uvicorn`. Filesystem de solo lectura en runtime (K8s).
- **matching-worker**: base `nvidia/cuda:12.2-cudnn8-runtime` (ArcFace/onnxruntime-gpu/faiss-gpu);
  fallback CPU documentado (SFace) si no hay GPU. Usuario no-root; sin puerto (consume SQS).
- Registro de imágenes: **Amazon ECR** (`ACCOUNT.dkr.ecr.sa-east-1.amazonaws.com/respuesta/<app>`).

**2. Dev local: `docker-compose` + LocalStack.** Postgres+pgvector, Redis y **LocalStack (SQS/SNS)**
emulan las dependencias gestionadas; un script de init crea colas (con **DLQ por redrive**) y topics.
boto3 honra `AWS_ENDPOINT_URL` → sin cambios de código entre local y AWS. El matching-worker queda
bajo perfil `gpu` (requiere NVIDIA Container Toolkit).

**3. Producción: EKS + kustomize.**
- **IRSA** (IAM Roles for Service Accounts) por workload → permisos **mínimos** (gateway:
  `sqs:SendMessage` a `meta-received`; matching: `sqs:Receive/Delete` + `sns:Publish`).
- **webhook-gateway**: Deployment + Service + **Ingress ALB** (AWS Load Balancer Controller, TLS por
  ACM) + **HPA** (CPU).
- **matching-worker**: Deployment en **nodos GPU** (`nvidia.com/gpu`, nodeSelector + toleration) +
  **KEDA** `ScaledObject` que escala por **profundidad de la cola** SQS.
- **Secretos** vía **External Secrets Operator** desde Vault/Secrets Manager (ADR-0008); nunca en la
  imagen ni en el ConfigMap.
- **Pod Security "restricted"**: `runAsNonRoot`, `readOnlyRootFilesystem` (donde aplica),
  `allowPrivilegeEscalation: false`, `drop: [ALL]`, `seccompProfile: RuntimeDefault`.

> Kubernetes da **portabilidad**: el mismo manifiesto corre en EKS y en un nodo **on-prem** (RTX 3090
> del MVP, ADR-0006/0013) unido al clúster como nodo GPU híbrido.

## Alternativas consideradas

| Opción | Pros | Contras |
| :---- | :---- | :---- |
| **A. EKS + kustomize (HTTP=ALB/HPA, workers=KEDA, GPU nodes)** ✅ | Soporta GPU y workers por cola; portable a on-prem; estándar K8s | Carga operativa de EKS; costo de nodos GPU |
| **B. ECS Fargate** | Menos ops | **Fargate no soporta GPU** → matching necesitaría EC2 igualmente; menos portable a on-prem |
| **C. EC2 + docker-compose** | Simple | Sin autoescalado declarativo ni self-healing; frágil bajo picos |
| **D. Lambda** | Serverless | Inviable para inferencia GPU sostenida y modelos grandes |

## Consecuencias

- **Positivas:** imágenes reproducibles y no-root; paridad local↔AWS; least-privilege por IRSA;
  autoescalado por cola (KEDA) y por CPU (HPA); portabilidad EKS↔on-prem para la GPU del MVP.
- **Negativas / deuda asumida:** operar EKS (add-ons: ALB controller, KEDA, External Secrets, NVIDIA
  device plugin); costo de nodos GPU; la imagen CUDA del matching es pesada (build/push lentos).
- **Impacto en threat model:** **A01** least-privilege por workload (IRSA); **A02** hardening de pods
  y de la config cloud; **A08** DLQ por redrive ya en SQS (ADR-0012). Los secretos no viven en la
  imagen (A05).

## Decisiones abiertas

- `<TODO>` IaC del clúster y add-ons (Terraform/eksctl); escaneo de imágenes en ECR + firma (cosign).
- `<TODO>` Cache de pesos InsightFace: `emptyDir` (descarga al arrancar) vs **EFS/PVC** compartido.
- `<TODO>` Política de `PodDisruptionBudget`, `NetworkPolicy` y límites de namespace.
- `<TODO>` Pipeline CI/CD (build → test → push ECR → `kubectl apply -k`) — Gate 4.

## Disparadores de revisión

- Aparece un servicio sin GPU y sin estado que encaje mejor en Fargate → evaluar híbrido.
- El costo de nodos GPU en EKS supera al on-prem → consolidar matching en el nodo híbrido on-prem.
