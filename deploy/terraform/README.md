# Terraform — Respuesta (CI/CD provisioning)

Infraestructura como código para provisionar AWS `sa-east-1` (ADR-0006) de forma
automatizada. Esta primera capa, **`bootstrap/`**, crea la **identidad y los roles
que el pipeline usa** para provisionar todo lo demás, más el **backend remoto de state**.

> Decisiones (este proyecto): IaC = **Terraform**; **dos roles separados**
> (bootstrap + deploy); auth = **access keys** de un usuario IAM.

## Modelo de identidad

```
GitHub Actions
   │  access key (larga vida) del usuario IAM ─ secrets AWS_CI_*
   ▼
respuesta-ci  (usuario IAM, SIN permisos de servicio)
   │  sts:AssumeRole + ExternalId
   ├──────────────► respuesta-tf-bootstrap   (infra base: IAM, KMS, EKS, VPC, ECR, SQS/SNS, S3, Secrets)
   └──────────────► respuesta-tf-deploy      (build/push ECR + deploy a EKS)
```

Por qué así, aun con access keys: el usuario **solo puede `AssumeRole`**. Una llave
filtrada, sin el `ExternalId` (un segundo secreto), **no puede asumir ningún rol ni
tocar recurso alguno**. Todo el privilegio real vive en los roles, acotado por un
**permissions boundary** que ninguna política puede sobrepasar (lock de región,
no-escalación de privilegios, protección de CloudTrail/GuardDuty).

> ⚠️ **Trade-off de las access keys:** son credenciales de larga vida. Rótalas cada
> ≤90 días, restringe a quién las ve, y considera migrar a **GitHub OIDC** (sin llaves)
> más adelante — el resto del diseño (roles, boundary, trust) no cambia, solo el
> `Principal` de la trust policy.

## Archivos

| Archivo | Qué define |
|---|---|
| `ci-identity.tf` | Usuario `respuesta-ci` (solo AssumeRole) |
| `roles.tf` | Roles `tf-bootstrap` y `tf-deploy` + trust con ExternalId |
| `permissions-boundary.tf` | Política boundary aplicada a usuario y roles |
| `backend-state.tf` | Bucket S3 (versionado, SSE-KMS, TLS-only) + DynamoDB lock + KMS key |
| `policies/permissions-boundary.json` | Techo de permisos + guardas |
| `policies/bootstrap-permissions.json` | Permisos del rol bootstrap |
| `policies/deploy-permissions.json` | Permisos del rol deploy |

## Orden de ejecución (una sola vez, por un admin)

La capa bootstrap arranca con **state local** porque es quien **crea** el backend.

```bash
cd deploy/terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
# edita external_id:  openssl rand -hex 16

terraform init
terraform apply        # crea usuario, roles, boundary y backend de state
```

Migra el state al backend remoto (recomendado):

```bash
# 1) descomenta el bloque backend "s3" en versions.tf
terraform init -migrate-state
```

Crea la access key del usuario CI (a mano — nunca en el state):

```bash
aws iam create-access-key --user-name respuesta-ci
# guarda AccessKeyId y SecretAccessKey UNA sola vez
```

## Secrets de GitHub Actions

`Settings > Secrets and variables > Actions`:

| Secret | Valor |
|---|---|
| `AWS_CI_ACCESS_KEY_ID` | AccessKeyId del paso anterior |
| `AWS_CI_SECRET_ACCESS_KEY` | SecretAccessKey del paso anterior |
| `AWS_ASSUME_EXTERNAL_ID` | el mismo `external_id` del tfvars |
| `AWS_BOOTSTRAP_ROLE_ARN` | output `tf_bootstrap_role_arn` |
| `AWS_DEPLOY_ROLE_ARN` | output `tf_deploy_role_arn` |

Crea también el environment **`production`** con *required reviewers* para que
`terraform apply` exija aprobación manual.

## Nota EKS (rol deploy)

`respuesta-tf-deploy` obtiene permiso IAM solo para `eks:DescribeCluster`. Para que
pueda **aplicar manifiestos** (`kubectl`/kustomize), su ARN debe mapearse en el
control de acceso del cluster: un **EKS access entry** (o el `aws-auth` ConfigMap)
con el grupo/permisos de despliegue adecuados. Eso se configura en la capa de infra
del cluster, no aquí.

## Siguiente paso

Con la identidad lista, las siguientes capas (`infra/` para VPC+EKS+ECR+colas+KMS, y
el workflow `deploy` de apps) se construyen sobre estos roles y el backend de state.
