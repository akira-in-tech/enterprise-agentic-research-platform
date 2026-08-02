output "github_deploy_role_arn" {
  description = "Role ARN configured as AWS_DEPLOY_ROLE_ARN in the protected GitHub environment."
  value       = aws_iam_role.github_deploy.arn
}

output "github_oidc_provider_arn" {
  description = "Account-level GitHub Actions OIDC provider ARN."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "github_oidc_subject" {
  description = "Exact immutable GitHub OIDC subject allowed by the role trust policy."
  value       = local.github_oidc_subject
}
