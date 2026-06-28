# ---------------------------------------------------------------------------
# Permissions boundary: techo de permisos para TODA identidad CI (el usuario,
# los dos roles de provisioning y cualquier role que el rol bootstrap cree).
# Define el "sobre" máximo + guardas que ninguna política puede sobrepasar.
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "ci_boundary" {
  name        = "${var.project}-ci-boundary"
  description = "Techo de permisos para identidades del pipeline CI/CD (${var.project})."
  policy = templatefile("${path.module}/policies/permissions-boundary.json", {
    account_id = var.account_id
    region     = var.region
    project    = var.project
  })
}
