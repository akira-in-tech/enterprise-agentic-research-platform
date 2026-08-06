variable "aws_region" {
  description = "AWS region for the staging environment."
  type        = string
  default     = "us-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region identifier."
  }
}

variable "project_name" {
  description = "Lowercase project identifier used in AWS resource names."
  type        = string
  default     = "evident-research"

  validation {
    condition = (
      length(var.project_name) >= 3 &&
      length(var.project_name) <= 24 &&
      can(regex("^[a-z0-9]+(?:-[a-z0-9]+)*$", var.project_name))
    )
    error_message = "project_name must be 3-24 lowercase letters, numbers, or single hyphens."
  }
}

variable "environment" {
  description = "Deployment environment. This stack is intentionally staging-only."
  type        = string
  default     = "staging"

  validation {
    condition     = var.environment == "staging"
    error_message = "This cost-controlled stack may only deploy the staging environment."
  }
}

variable "vpc_cidr" {
  description = "Private IPv4 range for the staging VPC."
  type        = string
  default     = "10.24.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be valid IPv4 CIDR notation."
  }
}

variable "availability_zone_count" {
  description = "Number of availability zones used for public and data subnets."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count >= 2 && var.availability_zone_count <= 3
    error_message = "availability_zone_count must be 2 or 3."
  }
}

variable "monthly_budget_limit_usd" {
  description = "Monthly AWS cost budget for this staging account."
  type        = number
  default     = 25

  validation {
    condition     = var.monthly_budget_limit_usd >= 5 && var.monthly_budget_limit_usd <= 200
    error_message = "monthly_budget_limit_usd must be between 5 and 200."
  }
}

variable "budget_notification_email" {
  description = "Email that receives 80% forecast and 100% actual budget alerts."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.budget_notification_email))
    error_message = "budget_notification_email must be a valid email address."
  }
}

variable "database_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "research_platform"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,62}$", var.database_name))
    error_message = "database_name must be a valid lowercase PostgreSQL identifier."
  }
}

variable "database_username" {
  description = "PostgreSQL administrator username whose password is managed by RDS."
  type        = string
  default     = "research_admin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,62}$", var.database_username))
    error_message = "database_username must be a valid lowercase PostgreSQL identifier."
  }
}

variable "database_instance_class" {
  description = "Small staging RDS instance class."
  type        = string
  default     = "db.t4g.micro"

  validation {
    condition     = startswith(var.database_instance_class, "db.")
    error_message = "database_instance_class must be an RDS instance class."
  }
}

variable "database_allocated_storage_gib" {
  description = "Initial encrypted PostgreSQL gp3 storage allocation."
  type        = number
  default     = 20

  validation {
    condition     = var.database_allocated_storage_gib >= 20 && var.database_allocated_storage_gib <= 50
    error_message = "database_allocated_storage_gib must be between 20 and 50 GiB."
  }
}

variable "cache_node_type" {
  description = "Single-node staging ElastiCache instance class."
  type        = string
  default     = "cache.t4g.micro"

  validation {
    condition     = startswith(var.cache_node_type, "cache.")
    error_message = "cache_node_type must be an ElastiCache node type."
  }
}

variable "api_image_tag" {
  description = "Immutable API image tag already pushed to ECR."
  type        = string
  default     = "bootstrap"

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$", var.api_image_tag))
    error_message = "api_image_tag must be a valid Docker image tag."
  }
}

variable "frontend_image_tag" {
  description = "Immutable frontend image tag already pushed to ECR."
  type        = string
  default     = "bootstrap"

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$", var.frontend_image_tag))
    error_message = "frontend_image_tag must be a valid Docker image tag."
  }
}

variable "application_desired_count" {
  description = "Number of running staging tasks. Keep zero until both immutable images are pushed."
  type        = number
  default     = 0

  validation {
    condition     = var.application_desired_count >= 0 && var.application_desired_count <= 2
    error_message = "application_desired_count must be between 0 and 2."
  }
}

variable "anthropic_model" {
  description = "Supported Anthropic model identifier used by the cloud staging path."
  type        = string
  default     = "replace-with-supported-model-id"

  validation {
    condition     = length(trimspace(var.anthropic_model)) >= 3
    error_message = "anthropic_model must not be blank."
  }
}

variable "milvus_uri" {
  description = "HTTPS endpoint for the external managed Milvus-compatible cluster."
  type        = string
  default     = "https://replace-with-managed-milvus-endpoint"

  validation {
    condition     = startswith(var.milvus_uri, "https://")
    error_message = "milvus_uri must use HTTPS."
  }
}

variable "milvus_collection" {
  description = "Tenant-scoped private-document collection name."
  type        = string
  default     = "private_document_chunks"

  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_]{0,254}$", var.milvus_collection))
    error_message = "milvus_collection must be a valid Milvus collection name."
  }
}
