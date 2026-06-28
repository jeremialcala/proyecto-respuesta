# ---------------------------------------------------------------------------
# Usuario IAM del pipeline. NO tiene permisos de servicio: su única capacidad
# es asumir los roles de provisioning (con ExternalId). Así, una access key
# filtrada por sí sola no puede tocar ningún recurso.
#
# La access key NO se crea en Terraform a propósito (el secreto quedaría en el
# state). Se genera a mano tras el primer apply — ver README.md.
# ---------------------------------------------------------------------------

resource "aws_iam_user" "ci" {
  name                 = "${var.project}-ci"
  permissions_boundary = aws_iam_policy.ci_boundary.arn
}

data "aws_iam_policy_document" "ci_assume_roles" {
  statement {
    sid     = "AssumeProvisioningRoles"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    resources = [
      aws_iam_role.tf_bootstrap.arn,
      aws_iam_role.tf_deploy.arn,
    ]
  }

  # El usuario no puede hacer nada más útil aunque su política fuera ampliada:
  # el boundary lo impide. Esto es defensa en profundidad.
  statement {
    sid       = "AllowReadOwnIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_user_policy" "ci_assume_roles" {
  name   = "assume-provisioning-roles"
  user   = aws_iam_user.ci.name
  policy = data.aws_iam_policy_document.ci_assume_roles.json
}
