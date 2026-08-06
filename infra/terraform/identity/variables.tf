variable "aws_region" {
  description = "AWS region used by the staging deployment role."
  type        = string
  default     = "us-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region identifier."
  }
}

variable "project_name" {
  description = "Project identifier used by staging AWS resources."
  type        = string
  default     = "evident-research"
}

variable "environment" {
  description = "Protected GitHub environment and AWS deployment environment."
  type        = string
  default     = "staging"

  validation {
    condition     = var.environment == "staging"
    error_message = "The deployment identity is restricted to staging."
  }
}

variable "state_bucket_prefix" {
  description = "Prefix of the account-scoped Terraform state bucket."
  type        = string
  default     = "evident-research-platform"
}

variable "github_owner" {
  description = "GitHub repository owner name."
  type        = string
  default     = "akira-in-tech"
}

variable "github_owner_id" {
  description = "Immutable GitHub owner identifier used in OIDC subject claims."
  type        = string
  default     = "109833555"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must contain only digits."
  }
}

variable "github_repository" {
  description = "GitHub repository name allowed to deploy staging."
  type        = string
  default     = "enterprise-agentic-research-platform"
}

variable "github_repository_id" {
  description = "Immutable GitHub repository identifier used in OIDC subject claims."
  type        = string
  default     = "1319710485"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain only digits."
  }
}
