output "state_bucket_name" {
  description = "S3 bucket used by environment stacks for remote Terraform state."
  value       = aws_s3_bucket.terraform_state.id
}

output "staging_backend_configuration" {
  description = "Non-secret partial backend configuration for the staging stack."
  value = {
    bucket       = aws_s3_bucket.terraform_state.id
    key          = "evident/staging/terraform.tfstate"
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}
