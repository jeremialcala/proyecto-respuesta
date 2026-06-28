# ---------------------------------------------------------------------------
# Roles de provisioning. Dos privilegios separados:
#   - tf-bootstrap : crea/gestiona la infra base (amplio, acotado por boundary).
#   - tf-deploy    : build/push ECR + deploy a EKS (mínimo privilegio).
# Ambos solo asumibles por el usuario CI y con ExternalId.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ci_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_user.ci.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }
  }
}

# ---- Rol BOOTSTRAP -------------------------------------------------------
resource "aws_iam_role" "tf_bootstrap" {
  name                 = "${var.project}-tf-bootstrap"
  description          = "Provisiona infra base de ${var.project} (IAM, KMS, EKS, VPC, ECR, SQS/SNS, S3, Secrets)."
  assume_role_policy   = data.aws_iam_policy_document.ci_trust.json
  permissions_boundary = aws_iam_policy.ci_boundary.arn
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "tf_bootstrap" {
  name = "bootstrap-permissions"
  role = aws_iam_role.tf_bootstrap.id
  policy = templatefile("${path.module}/policies/bootstrap-permissions.json", {
    account_id   = var.account_id
    region       = var.region
    project      = var.project
    boundary_arn = aws_iam_policy.ci_boundary.arn
  })
}

# ---- Rol DEPLOY ----------------------------------------------------------
resource "aws_iam_role" "tf_deploy" {
  name                 = "${var.project}-tf-deploy"
  description          = "Build/push de imágenes a ECR y deploy de manifiestos a EKS para ${var.project}."
  assume_role_policy   = data.aws_iam_policy_document.ci_trust.json
  permissions_boundary = aws_iam_policy.ci_boundary.arn
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "tf_deploy" {
  name = "deploy-permissions"
  role = aws_iam_role.tf_deploy.id
  policy = templatefile("${path.module}/policies/deploy-permissions.json", {
    account_id = var.account_id
    region     = var.region
    project    = var.project
  })
}
