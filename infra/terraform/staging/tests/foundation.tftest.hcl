mock_provider "aws" {}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-west-2a", "us-west-2b", "us-west-2c"]
  }
}

override_data {
  target = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing
  values = {
    id   = "pl-cloudfront"
    name = "com.amazonaws.global.cloudfront.origin-facing"
  }
}

override_data {
  target = data.aws_cloudfront_cache_policy.optimized
  values = {
    id = "managed-caching-optimized"
  }
}

override_data {
  target = data.aws_cloudfront_cache_policy.disabled
  values = {
    id = "managed-caching-disabled"
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

  assert {
    condition     = aws_db_instance.postgres.publicly_accessible == false
    error_message = "PostgreSQL must remain private."
  }

  assert {
    condition     = aws_db_instance.postgres.multi_az == false
    error_message = "The disposable staging database must remain single-AZ for cost control."
  }

  assert {
    condition     = aws_db_instance.postgres.storage_encrypted == true
    error_message = "PostgreSQL storage must be encrypted."
  }

  assert {
    condition     = aws_elasticache_replication_group.cache.num_cache_clusters == 1
    error_message = "The disposable staging cache must remain single-node for cost control."
  }

  assert {
    condition     = aws_elasticache_replication_group.cache.transit_encryption_enabled == true
    error_message = "Cache traffic must use TLS."
  }

  assert {
    condition     = aws_ecs_task_definition.application.cpu == "512"
    error_message = "The staging task must remain on the cost-controlled 0.5-vCPU size."
  }

  assert {
    condition     = aws_ecs_task_definition.application.memory == "1024"
    error_message = "The staging task must remain on the cost-controlled 1-GiB size."
  }

  assert {
    condition     = aws_ecs_service.application.desired_count == 0
    error_message = "The default apply must not start billable tasks before images and secrets are ready."
  }

  assert {
    condition     = aws_ecs_service.application.network_configuration[0].assign_public_ip == true
    error_message = "The NAT-free task requires explicit public egress."
  }

  assert {
    condition     = aws_cloudwatch_log_group.application.retention_in_days == 7
    error_message = "Staging logs must use bounded retention."
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.private_documents.block_public_acls,
      aws_s3_bucket_public_access_block.private_documents.block_public_policy,
      aws_s3_bucket_public_access_block.private_documents.ignore_public_acls,
      aws_s3_bucket_public_access_block.private_documents.restrict_public_buckets,
    ])
    error_message = "Private document storage must block every form of public S3 access."
  }

  assert {
    condition = one(flatten([
      for rule in aws_s3_bucket_server_side_encryption_configuration.private_documents.rule : [
        for encryption in rule.apply_server_side_encryption_by_default : encryption.sse_algorithm
      ]
    ])) == "AES256"
    error_message = "Private document storage must use server-side encryption."
  }

  assert {
    condition     = aws_s3_bucket_versioning.private_documents.versioning_configuration[0].status == "Enabled"
    error_message = "Private document storage must retain recoverable object versions."
  }

  assert {
    condition     = one([for item in local.api_container_environment : item.value if item.name == "EMBEDDING_PROVIDER"]) == "bedrock"
    error_message = "AWS staging must use the external Bedrock embedding provider."
  }

  assert {
    condition     = one([for item in local.api_container_environment : item.value if item.name == "DOCUMENT_STORAGE_PROVIDER"]) == "s3"
    error_message = "AWS staging must store private source objects in S3."
  }

  assert {
    condition     = contains(local.private_knowledge_bedrock_actions, "bedrock:InvokeModel")
    error_message = "The application task role must be able to invoke the configured embedding model."
  }
}
