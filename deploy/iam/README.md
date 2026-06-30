# Políticas IAM — Respuesta (EKS / IRSA)

Políticas de permiso **least-privilege**, una por workload, según ADR-0014 (IRSA por
workload), ADR-0012 (broker SQS/SNS) y ADR-0006 (residencia en `sa-east-1`). Cada workload
recibe su propio IAM role; **no hay un rol compartido**. Todas las acciones quedan acotadas a
ARNs concretos y a `sa-east-1` mediante la condición `aws:RequestedRegion`.

## Archivos

| Archivo | Workload | Resumen de permisos |
|---|---|---|
| `webhook-gateway.policy.json` | Webhook Gateway (FastAPI, ALB) | `sns:Publish` a `meta-received`; leer verify-token + clave HMAC |
| `meta-handler.policy.json` | Meta Handler (worker) | Consumir `meta-received`; publicar `inbound-text`/`inbound-media`; KMS evento (JWK/JWE) |
| `vault-control-worker.policy.json` | Worker de Bóveda (zona restringida) | Consumir `inbound-media`; `s3:PutObject` cifrado; KMS medios (envelope); publicar `media-stored` |
| `matching-engine.policy.json` | Motor de matching (GPU, KEDA) | Consumir `media-stored`; `s3:GetObject`; `kms:Decrypt` medios; publicar `candidate-generated` |
| `portal-backoffice.policy.json` | Portal + Back office (NestJS) | Secrets (Auth0/DB/Redis); S3 medios; KMS PII+medios (ver en claro, auditado); publicar eventos de dominio |
| `outbound-service.policy.json` | Servicio de salida | Consumir `outbound-reply`; leer token Graph API |
| `media-gateway.policy.json` | Media Gateway (ALB + mesh interno) | `kms:GenerateMac`/`VerifyMac` (HMAC del token); `s3:GetObject` + `kms:Decrypt` (servir la foto, ADR-0017/0020) |
| `keda-operator.policy.json` | KEDA operator | `sqs:GetQueueAttributes` + `cloudwatch:GetMetricData` para escalar |
| `irsa-trust-policy.template.json` | (todos) | Plantilla de trust policy: assume-role vía OIDC del cluster EKS |

## Placeholders a sustituir

- `ACCOUNT_ID` — ID de cuenta AWS (12 dígitos).
- `KEY_ID_MEDIA` / `KEY_ID_PII` / `KEY_ID_EVENTS` — IDs de las KMS keys. **Mantén las keys
  separadas por dominio** (medios vs PII) para que matching no pueda descifrar PII de back office.
- `KEY_ID_TOKEN_HMAC` — ID de la KMS key HMAC que firma los tokens del media-gateway (ADR-0017).
- `EKS_OIDC_ID` — ID del OIDC provider del cluster (`aws eks describe-cluster ... identity.oidc.issuer`).
- `SERVICE_ACCOUNT_NAME` — nombre del ServiceAccount k8s en el namespace `respuesta`.

## Convención de nombres de recursos

- **SNS topics / SQS queues:** `respuesta-<evento>` (p.ej. `respuesta-meta-received`,
  `respuesta-candidate-generated`). Cada cola con su DLQ `respuesta-<evento>-dlq` (redrive).
- **Bucket S3:** `respuesta-media`, prefijo `encrypted/` para binarios cifrados con sobre.
- **Secrets:** prefijo `respuesta/` (`respuesta/meta/*`, `respuesta/auth0`, `respuesta/db`, …).

## Crear un role IRSA (ejemplo: matching-engine)

```bash
ACCOUNT_ID=123456789012
# 1) trust policy desde la plantilla (sustituye EKS_OIDC_ID y SERVICE_ACCOUNT_NAME)
aws iam create-role \
  --role-name respuesta-matching-engine \
  --assume-role-policy-document file://irsa-trust-policy.template.json

# 2) política de permisos del workload
aws iam put-role-policy \
  --role-name respuesta-matching-engine \
  --policy-name matching-engine \
  --policy-document file://matching-engine.policy.json
```

Luego anota el ServiceAccount:
`eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/respuesta-matching-engine`.

## Notas

- **SSE-KMS en colas/secretos:** si SQS/SNS/Secrets usan una CMK propia (no la AWS-managed),
  añade `kms:Decrypt` / `kms:GenerateDataKey` sobre esa key a los productores/consumidores.
- **Roles de plataforma** (no incluidos aquí, usan policies AWS-managed): node group
  (`AmazonEKSWorkerNodePolicy`, `AmazonEKS_CNI_Policy`, `AmazonEC2ContainerRegistryReadOnly`),
  cluster (`AmazonEKSClusterPolicy`), AWS Load Balancer Controller, EBS CSI driver,
  Cluster Autoscaler/Karpenter.
- **Observabilidad:** Signoz es on-prem; si algún workload escribe a CloudWatch Logs, añade
  `logs:CreateLogStream` + `logs:PutLogEvents` sobre su log group.
