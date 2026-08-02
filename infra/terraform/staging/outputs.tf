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
