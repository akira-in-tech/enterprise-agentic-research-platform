variable "aws_region" {
  description = "AWS region that stores the shared Terraform state bucket."
  type        = string
  default     = "us-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region identifier."
  }
}

variable "project_name" {
  description = "Lowercase project identifier used in globally unique resource names."
  type        = string
  default     = "evident-research-platform"

  validation {
    condition = (
      length(var.project_name) >= 3 &&
      length(var.project_name) <= 32 &&
      can(regex("^[a-z0-9]+(?:-[a-z0-9]+)*$", var.project_name))
    )
    error_message = "project_name must be 3-32 lowercase letters, numbers, or single hyphens."
  }
}
