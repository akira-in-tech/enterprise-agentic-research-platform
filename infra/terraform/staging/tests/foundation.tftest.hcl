mock_provider "aws" {}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-west-2a", "us-west-2b", "us-west-2c"]
  }
}

run "cost_controlled_foundation" {
  command = plan

  variables {
    budget_notification_email = "alerts@example.com"
  }

  assert {
    condition     = length(aws_subnet.public) == 2
    error_message = "The staging foundation must create two public subnets."
  }

  assert {
    condition     = length(aws_subnet.data) == 2
    error_message = "The staging foundation must create two isolated data subnets."
  }

  assert {
    condition = alltrue([
      for subnet in aws_subnet.public : subnet.map_public_ip_on_launch == false
    ])
    error_message = "Public IP assignment must be explicit at the Fargate service, not inherited by every subnet resource."
  }

  assert {
    condition = alltrue([
      for subnet in aws_subnet.data : subnet.map_public_ip_on_launch == false
    ])
    error_message = "Data subnets must never assign public IP addresses."
  }

  assert {
    condition     = aws_ecr_repository.api.image_tag_mutability == "IMMUTABLE"
    error_message = "API deployment images must use immutable tags."
  }

  assert {
    condition     = aws_ecr_repository.frontend.image_tag_mutability == "IMMUTABLE"
    error_message = "Frontend deployment images must use immutable tags."
  }

  assert {
    condition     = aws_budgets_budget.staging.limit_amount == "25"
    error_message = "The default staging budget must remain capped at 25 USD."
  }
}
