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
