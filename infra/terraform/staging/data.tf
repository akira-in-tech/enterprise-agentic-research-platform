resource "aws_db_subnet_group" "postgres" {
  name       = "${local.name_prefix}-postgres"
  subnet_ids = values(aws_subnet.data)[*].id

  tags = {
    Name = "${local.name_prefix}-postgres"
  }
}

resource "aws_db_instance" "postgres" {
  identifier = "${local.name_prefix}-postgres"

  engine         = "postgres"
  instance_class = var.database_instance_class
  port           = 5432

  db_name                     = var.database_name
  username                    = var.database_username
  manage_master_user_password = true

  allocated_storage     = var.database_allocated_storage_gib
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = 1
  copy_tags_to_snapshot   = true
  deletion_protection     = false
  skip_final_snapshot     = true

  auto_minor_version_upgrade   = true
  apply_immediately            = true
  performance_insights_enabled = false

  tags = {
    Name = "${local.name_prefix}-postgres"
  }
}

resource "aws_elasticache_subnet_group" "cache" {
  name       = "${local.name_prefix}-cache"
  subnet_ids = values(aws_subnet.data)[*].id
}

resource "random_password" "cache_auth_token" {
  length  = 48
  special = false
}

resource "aws_elasticache_replication_group" "cache" {
  replication_group_id = "${local.name_prefix}-cache"
  description          = "Disposable staging coordination and result cache"

  engine                     = "valkey"
  node_type                  = var.cache_node_type
  port                       = 6379
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  subnet_group_name  = aws_elasticache_subnet_group.cache.name
  security_group_ids = [aws_security_group.cache.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.cache_auth_token.result

  snapshot_retention_limit = 0
  apply_immediately        = true

  tags = {
    Name = "${local.name_prefix}-cache"
  }
}

resource "aws_secretsmanager_secret" "cache" {
  name                    = "${local.name_prefix}/cache"
  description             = "Generated staging cache connection details"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "cache" {
  secret_id = aws_secretsmanager_secret.cache.id
  secret_string = jsonencode({
    auth_token = random_password.cache_auth_token.result
  })
}

resource "aws_secretsmanager_secret" "providers" {
  name                    = "${local.name_prefix}/providers"
  description             = "External LLM, search, and managed Milvus credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "providers" {
  secret_id = aws_secretsmanager_secret.providers.id
  secret_string = jsonencode({
    ANTHROPIC_API_KEY = "replace-after-apply"
    MILVUS_TOKEN      = "replace-after-apply"
    TAVILY_API_KEY    = "replace-after-apply"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
