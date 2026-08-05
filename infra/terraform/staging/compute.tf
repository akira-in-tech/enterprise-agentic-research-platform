data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/ecs/${local.name_prefix}/application"
  retention_in_days = 7
}

resource "aws_ecs_cluster" "this" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name_prefix}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "read-application-secrets"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadApplicationSecrets"
        Effect = "Allow"
        Action = "secretsmanager:GetSecretValue"
        Resource = [
          aws_db_instance.postgres.master_user_secret[0].secret_arn,
          aws_secretsmanager_secret.cache.arn,
          aws_secretsmanager_secret.providers.arn,
        ]
      },
    ]
  })
}

resource "aws_iam_role" "ecs_task" {
  name = "${local.name_prefix}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_lb" "application" {
  name                       = substr("${local.name_prefix}-alb", 0, 32)
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.load_balancer.id]
  subnets                    = values(aws_subnet.public)[*].id
  enable_deletion_protection = false
  idle_timeout               = 4000

  drop_invalid_header_fields = true

  tags = {
    Name = "${local.name_prefix}-alb"
  }
}

resource "aws_lb_target_group" "application" {
  name        = substr("${local.name_prefix}-app", 0, 32)
  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id

  deregistration_delay = 30

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    path                = "/api/health"
    protocol            = "HTTP"
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.application.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.application.arn
  }
}

locals {
  api_container_environment = [
    { name = "APP_ENV", value = var.environment },
    { name = "APP_DEBUG", value = "false" },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "LLM_PROVIDER", value = "anthropic" },
    { name = "ANTHROPIC_MODEL", value = var.anthropic_model },
    { name = "VECTOR_STORE_PROVIDER", value = "milvus" },
    { name = "MILVUS_URI", value = var.milvus_uri },
    { name = "MILVUS_COLLECTION", value = var.milvus_collection },
    { name = "EMBEDDING_PROVIDER", value = "bedrock" },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "BEDROCK_EMBEDDING_MODEL", value = "amazon.titan-embed-text-v2:0" },
    { name = "BEDROCK_EMBEDDING_DIMENSIONS", value = "1024" },
    { name = "DOCUMENT_STORAGE_PROVIDER", value = "s3" },
    { name = "DOCUMENT_S3_BUCKET", value = aws_s3_bucket.private_documents.bucket },
    { name = "MCP_ENDPOINT", value = "http://127.0.0.1:8001/mcp" },
    { name = "MCP_SERVER_NAME", value = "evident-reference" },
    { name = "POSTGRES_HOST", value = aws_db_instance.postgres.address },
    { name = "POSTGRES_DB", value = var.database_name },
    { name = "POSTGRES_USER", value = var.database_username },
    { name = "REDIS_HOST", value = aws_elasticache_replication_group.cache.primary_endpoint_address },
    { name = "OLLAMA_BASE_URL", value = "http://127.0.0.1:11434" },
    { name = "OLLAMA_MODEL", value = "qwen3:8b" },
    { name = "OLLAMA_EMBEDDING_MODEL", value = "qwen3-embedding:0.6b" },
    { name = "OLLAMA_EMBEDDING_DIMENSIONS", value = "1024" },
  ]

  api_container_secrets = [
    {
      name      = "POSTGRES_PASSWORD"
      valueFrom = "${aws_db_instance.postgres.master_user_secret[0].secret_arn}:password::"
    },
    {
      name      = "REDIS_AUTH_TOKEN"
      valueFrom = "${aws_secretsmanager_secret.cache.arn}:auth_token::"
    },
    {
      name      = "ANTHROPIC_API_KEY"
      valueFrom = "${aws_secretsmanager_secret.providers.arn}:ANTHROPIC_API_KEY::"
    },
    {
      name      = "TAVILY_API_KEY"
      valueFrom = "${aws_secretsmanager_secret.providers.arn}:TAVILY_API_KEY::"
    },
    {
      name      = "MILVUS_TOKEN"
      valueFrom = "${aws_secretsmanager_secret.providers.arn}:MILVUS_TOKEN::"
    },
  ]
}

resource "aws_ecs_task_definition" "application" {
  family                   = local.name_prefix
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([
    {
      name        = "api"
      image       = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
      essential   = true
      command     = ["python", "-m", "app.entrypoint"]
      environment = local.api_container_environment
      secrets     = local.api_container_secrets
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        },
      ]
      dependsOn = [
        {
          containerName = "mcp"
          condition     = "HEALTHY"
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.application.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    },
    {
      name      = "mcp"
      image     = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
      essential = true
      command   = ["python", "-m", "app.mcp_server"]
      environment = [
        { name = "APP_ENV", value = var.environment },
        { name = "LOG_LEVEL", value = "INFO" },
        { name = "MCP_SERVER_NAME", value = "evident-reference" },
        { name = "MCP_SERVER_HOST", value = "0.0.0.0" },
        { name = "MCP_SERVER_PORT", value = "8001" },
      ]
      portMappings = [
        {
          containerPort = 8001
          hostPort      = 8001
          protocol      = "tcp"
        },
      ]
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)\""]
        interval    = 10
        timeout     = 3
        retries     = 5
        startPeriod = 5
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.application.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "mcp"
        }
      }
    },
    {
      name      = "frontend"
      image     = "${aws_ecr_repository.frontend.repository_url}:${var.frontend_image_tag}"
      essential = true
      environment = [
        {
          name  = "API_UPSTREAM"
          value = "127.0.0.1:8000"
        },
      ]
      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
          protocol      = "tcp"
        },
      ]
      dependsOn = [
        {
          containerName = "api"
          condition     = "START"
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.application.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "frontend"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "application" {
  name            = "${local.name_prefix}-application"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.application.arn
  desired_count   = var.application_desired_count
  launch_type     = "FARGATE"

  platform_version = "1.4.0"

  network_configuration {
    subnets          = values(aws_subnet.public)[*].id
    security_groups  = [aws_security_group.application.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.application.arn
    container_name   = "frontend"
    container_port   = 80
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  health_check_grace_period_seconds = 120

  depends_on = [
    aws_iam_role_policy_attachment.ecs_execution,
    aws_iam_role_policy.ecs_execution_secrets,
    aws_iam_role_policy.ecs_task_private_knowledge,
    aws_lb_listener.http,
  ]
}
