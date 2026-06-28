output "ci_user_name" {
  description = "Usuario IAM del pipeline (genera su access key a mano)."
  value       = aws_iam_user.ci.name
}

output "ci_user_arn" {
  value = aws_iam_user.ci.arn
}

output "tf_bootstrap_role_arn" {
  description = "ARN del rol de provisioning de infra base (secret AWS_BOOTSTRAP_ROLE_ARN)."
  value       = aws_iam_role.tf_bootstrap.arn
}

output "tf_deploy_role_arn" {
  description = "ARN del rol de deploy de apps (secret AWS_DEPLOY_ROLE_ARN)."
  value       = aws_iam_role.tf_deploy.arn
}

output "permissions_boundary_arn" {
  value = aws_iam_policy.ci_boundary.arn
}

output "tfstate_bucket" {
  value = aws_s3_bucket.tfstate.id
}

output "tflock_table" {
  value = aws_dynamodb_table.tflock.name
}

output "tfstate_kms_alias" {
  value = aws_kms_alias.tfstate.name
}
