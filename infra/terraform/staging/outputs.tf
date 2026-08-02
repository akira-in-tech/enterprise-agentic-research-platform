output "vpc_id" {
  description = "Staging VPC identifier."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs used by the ALB and NAT-free Fargate tasks."
  value       = values(aws_subnet.public)[*].id
}

output "data_subnet_ids" {
  description = "Isolated subnet IDs reserved for PostgreSQL and Redis."
  value       = values(aws_subnet.data)[*].id
}

output "api_repository_url" {
  description = "ECR repository URL for the FastAPI image."
  value       = aws_ecr_repository.api.repository_url
}

output "frontend_repository_url" {
  description = "ECR repository URL for the Vue and Nginx image."
  value       = aws_ecr_repository.frontend.repository_url
}

output "database_endpoint" {
  description = "Private RDS PostgreSQL endpoint."
  value       = aws_db_instance.postgres.address
}

output "database_master_secret_arn" {
  description = "AWS-managed Secrets Manager ARN for the PostgreSQL master credentials."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "cache_endpoint" {
  description = "Private TLS ElastiCache primary endpoint."
  value       = aws_elasticache_replication_group.cache.primary_endpoint_address
}

output "provider_secret_arn" {
  description = "Secrets Manager ARN whose placeholder external provider keys must be replaced after apply."
  value       = aws_secretsmanager_secret.providers.arn
}

output "application_url" {
  description = "CloudFront HTTPS URL for the staging research console and API."
  value       = "https://${aws_cloudfront_distribution.application.domain_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster used by deployment automation."
  value       = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  description = "ECS service used by deployment automation."
  value       = aws_ecs_service.application.name
}
