locals {
  name_prefix = "${var.project_name}-${var.environment}"
  selected_availability_zones = slice(
    data.aws_availability_zones.available.names,
    0,
    var.availability_zone_count,
  )

  common_tags = {
    Application = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Repository  = "enterprise-agentic-research-platform"
    CostCenter  = "portfolio-staging"
  }
}
