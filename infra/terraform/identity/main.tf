data "aws_caller_identity" "current" {}

locals {
  account_id             = data.aws_caller_identity.current.account_id
  name_prefix            = "${var.project_name}-${var.environment}"
  state_bucket_name      = "${var.state_bucket_prefix}-${local.account_id}-tfstate"
  github_oidc_host       = "token.actions.githubusercontent.com"
  github_oidc_subject    = "repo:${var.github_owner}@${var.github_owner_id}/${var.github_repository}@${var.github_repository_id}:environment:${var.environment}"
  ecs_execution_role     = "${local.name_prefix}-ecs-execution"
  ecs_task_role          = "${local.name_prefix}-ecs-task"
  ecs_execution_role_arn = "arn:aws:iam::${local.account_id}:role/${local.ecs_execution_role}"
  ecs_task_role_arn      = "arn:aws:iam::${local.account_id}:role/${local.ecs_task_role}"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.github_oidc_host}"
  client_id_list = ["sts.amazonaws.com"]

  tags = {
    Name = "GitHub Actions"
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${local.name_prefix}-github-deploy"
  description          = "Short-lived GitHub OIDC role for Evident staging deployments"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GitHubStagingEnvironment"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.github_oidc_host}:aud" = "sts.amazonaws.com"
            "${local.github_oidc_host}:sub" = local.github_oidc_subject
          }
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "terraform_state" {
  name = "terraform-staging-state"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "StateBucketMetadata"
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket",
        ]
        Resource = "arn:aws:s3:::${local.state_bucket_name}"
      },
      {
        Sid    = "StagingStateObjects"
        Effect = "Allow"
        Action = [
          "s3:DeleteObject",
          "s3:GetObject",
          "s3:PutObject",
        ]
        Resource = [
          "arn:aws:s3:::${local.state_bucket_name}/evident/staging/terraform.tfstate",
          "arn:aws:s3:::${local.state_bucket_name}/evident/staging/terraform.tfstate.tflock",
        ]
      },
    ]
  })
}

resource "aws_iam_role_policy" "regional_staging" {
  name = "manage-regional-staging"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RegionalReadAndDiscovery"
        Effect = "Allow"
        Action = [
          "ec2:DescribeAccountAttributes",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeManagedPrefixLists",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeRouteTables",
          "ec2:DescribeSecurityGroupRules",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSubnets",
          "ec2:DescribeTags",
          "ec2:DescribeVpcAttribute",
          "ec2:DescribeVpcs",
          "ec2:GetManagedPrefixListEntries",
          "ec2:GetSecurityGroupsForVpc",
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetLifecyclePolicy",
          "ecr:GetRepositoryPolicy",
          "ecr:ListTagsForResource",
          "ecs:DescribeClusters",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeTasks",
          "ecs:ListTagsForResource",
          "elasticache:DescribeCacheClusters",
          "elasticache:DescribeCacheSubnetGroups",
          "elasticache:DescribeReplicationGroups",
          "elasticache:ListTagsForResource",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeLoadBalancerAttributes",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTags",
          "elasticloadbalancing:DescribeTargetGroupAttributes",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth",
          "logs:DescribeLogGroups",
          "logs:ListTagsForResource",
          "rds:DescribeDBInstances",
          "rds:DescribeDBSubnetGroups",
          "rds:ListTagsForResource",
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:ListSecretVersionIds",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
      {
        Sid    = "ManageStagingNetwork"
        Effect = "Allow"
        Action = [
          "ec2:AssociateRouteTable",
          "ec2:AttachInternetGateway",
          "ec2:AuthorizeSecurityGroupEgress",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:CreateInternetGateway",
          "ec2:CreateRoute",
          "ec2:CreateRouteTable",
          "ec2:CreateSecurityGroup",
          "ec2:CreateSubnet",
          "ec2:CreateTags",
          "ec2:CreateVpc",
          "ec2:DeleteInternetGateway",
          "ec2:DeleteRoute",
          "ec2:DeleteRouteTable",
          "ec2:DeleteSecurityGroup",
          "ec2:DeleteSubnet",
          "ec2:DeleteTags",
          "ec2:DeleteVpc",
          "ec2:DetachInternetGateway",
          "ec2:DisassociateRouteTable",
          "ec2:ModifySecurityGroupRules",
          "ec2:ModifySubnetAttribute",
          "ec2:ModifyVpcAttribute",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
      {
        Sid    = "ManageStagingEcr"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:CreateRepository",
          "ecr:DeleteLifecyclePolicy",
          "ecr:DeleteRepository",
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetLifecyclePolicy",
          "ecr:InitiateLayerUpload",
          "ecr:ListTagsForResource",
          "ecr:PutImage",
          "ecr:PutImageScanningConfiguration",
          "ecr:PutImageTagMutability",
          "ecr:PutLifecyclePolicy",
          "ecr:TagResource",
          "ecr:UntagResource",
          "ecr:UploadLayerPart",
        ]
        Resource = [
          "arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${local.name_prefix}-api",
          "arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${local.name_prefix}-frontend",
        ]
      },
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "ManageStagingDataServices"
        Effect = "Allow"
        Action = [
          "elasticache:AddTagsToResource",
          "elasticache:CreateCacheSubnetGroup",
          "elasticache:CreateReplicationGroup",
          "elasticache:DeleteCacheSubnetGroup",
          "elasticache:DeleteReplicationGroup",
          "elasticache:DescribeCacheSubnetGroups",
          "elasticache:DescribeReplicationGroups",
          "elasticache:ListTagsForResource",
          "elasticache:ModifyCacheSubnetGroup",
          "elasticache:ModifyReplicationGroup",
          "elasticache:RemoveTagsFromResource",
          "rds:AddTagsToResource",
          "rds:CreateDBInstance",
          "rds:CreateDBSubnetGroup",
          "rds:DeleteDBInstance",
          "rds:DeleteDBSubnetGroup",
          "rds:DescribeDBInstances",
          "rds:DescribeDBSubnetGroups",
          "rds:ListTagsForResource",
          "rds:ModifyDBInstance",
          "rds:ModifyDBSubnetGroup",
          "rds:RemoveTagsFromResource",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
      {
        Sid    = "ManageStagingSecretsAndLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:DeleteRetentionPolicy",
          "logs:DescribeLogGroups",
          "logs:ListTagsForResource",
          "logs:PutRetentionPolicy",
          "logs:TagResource",
          "logs:UntagResource",
          "secretsmanager:CreateSecret",
          "secretsmanager:DeleteSecret",
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:ListSecretVersionIds",
          "secretsmanager:PutSecretValue",
          "secretsmanager:TagResource",
          "secretsmanager:UntagResource",
        ]
        Resource = [
          "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/ecs/${local.name_prefix}/application",
          "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/ecs/${local.name_prefix}/application:*",
          "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:${local.name_prefix}/*",
        ]
      },
      {
        Sid    = "ManageStagingEcs"
        Effect = "Allow"
        Action = [
          "ecs:CreateCluster",
          "ecs:CreateService",
          "ecs:DeleteCluster",
          "ecs:DeleteService",
          "ecs:DeregisterTaskDefinition",
          "ecs:DescribeClusters",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeTasks",
          "ecs:ListTagsForResource",
          "ecs:RegisterTaskDefinition",
          "ecs:TagResource",
          "ecs:UntagResource",
          "ecs:UpdateClusterSettings",
          "ecs:UpdateService",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
      {
        Sid    = "ManageStagingLoadBalancer"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:AddTags",
          "elasticloadbalancing:CreateListener",
          "elasticloadbalancing:CreateLoadBalancer",
          "elasticloadbalancing:CreateTargetGroup",
          "elasticloadbalancing:DeleteListener",
          "elasticloadbalancing:DeleteLoadBalancer",
          "elasticloadbalancing:DeleteTargetGroup",
          "elasticloadbalancing:DeregisterTargets",
          "elasticloadbalancing:DescribeListenerAttributes",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeLoadBalancerAttributes",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTags",
          "elasticloadbalancing:DescribeTargetGroupAttributes",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:ModifyLoadBalancerAttributes",
          "elasticloadbalancing:ModifyTargetGroup",
          "elasticloadbalancing:ModifyTargetGroupAttributes",
          "elasticloadbalancing:RegisterTargets",
          "elasticloadbalancing:RemoveTags",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "global_staging" {
  name = "manage-global-staging"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManageStagingCloudFront"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateDistribution",
          "cloudfront:CreateInvalidation",
          "cloudfront:CreateOriginRequestPolicy",
          "cloudfront:DeleteDistribution",
          "cloudfront:DeleteOriginRequestPolicy",
          "cloudfront:GetCachePolicy",
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:GetOriginRequestPolicy",
          "cloudfront:GetOriginRequestPolicyConfig",
          "cloudfront:ListCachePolicies",
          "cloudfront:ListDistributions",
          "cloudfront:ListOriginRequestPolicies",
          "cloudfront:ListTagsForResource",
          "cloudfront:TagResource",
          "cloudfront:UntagResource",
          "cloudfront:UpdateDistribution",
          "cloudfront:UpdateOriginRequestPolicy",
        ]
        Resource = "*"
      },
      {
        Sid    = "ManageStagingBudget"
        Effect = "Allow"
        Action = [
          "budgets:DeleteBudget",
          "budgets:ListTagsForResource",
          "budgets:ModifyBudget",
          "budgets:TagResource",
          "budgets:UntagResource",
          "budgets:ViewBudget",
        ]
        Resource = "arn:aws:budgets::${local.account_id}:budget/${local.name_prefix}-monthly"
      },
      {
        Sid    = "ManageProjectEcsRoles"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:DeleteRolePolicy",
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:ListRolePolicies",
          "iam:PutRolePolicy",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:UpdateAssumeRolePolicy",
        ]
        Resource = [
          local.ecs_execution_role_arn,
          local.ecs_task_role_arn,
        ]
      },
      {
        Sid    = "AttachEcsExecutionManagedPolicy"
        Effect = "Allow"
        Action = [
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
        ]
        Resource = local.ecs_execution_role_arn
        Condition = {
          ArnEquals = {
            "iam:PolicyARN" = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
          }
        }
      },
      {
        Sid    = "PassProjectRolesToEcsOnly"
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          local.ecs_execution_role_arn,
          local.ecs_task_role_arn,
        ]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      },
      {
        Sid      = "CreateRequiredServiceLinkedRoles"
        Effect   = "Allow"
        Action   = "iam:CreateServiceLinkedRole"
        Resource = "arn:aws:iam::${local.account_id}:role/aws-service-role/*"
        Condition = {
          StringEquals = {
            "iam:AWSServiceName" = [
              "ecs.amazonaws.com",
              "elasticache.amazonaws.com",
              "elasticloadbalancing.amazonaws.com",
              "rds.amazonaws.com",
            ]
          }
        }
      },
    ]
  })
}

# A customer-managed policy, not another inline one: IAM enforces a combined
# 10240-byte ceiling across ALL of a role's inline policies together (not
# per document), and regional_staging + global_staging + terraform_state
# were already close to it before this statement set existed. A managed
# policy has its own separate size budget and headroom for what the next
# deploy attempt inevitably still needs.
resource "aws_iam_policy" "staging_storage_and_secrets" {
  name = "${local.name_prefix}-storage-and-secrets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManageStagingDocumentBucket"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:DeleteBucket",
          "s3:DeleteBucketPolicy",
          "s3:DeleteObject",
          "s3:GetBucketAcl",
          "s3:GetBucketPolicy",
          "s3:GetBucketPublicAccessBlock",
          "s3:GetBucketTagging",
          "s3:GetBucketVersioning",
          "s3:GetEncryptionConfiguration",
          "s3:GetLifecycleConfiguration",
          "s3:ListBucket",
          "s3:PutBucketPolicy",
          "s3:PutBucketPublicAccessBlock",
          "s3:PutBucketTagging",
          "s3:PutBucketVersioning",
          "s3:PutEncryptionConfiguration",
          "s3:PutLifecycleConfiguration",
        ]
        Resource = [
          "arn:aws:s3:::${local.name_prefix}-*-documents",
          "arn:aws:s3:::${local.name_prefix}-*-documents/*",
        ]
      },
      {
        Sid    = "ManageStagingRdsManagedSecret"
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:DeleteSecret",
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:ListSecretVersionIds",
          "secretsmanager:PutSecretValue",
          "secretsmanager:TagResource",
          "secretsmanager:UntagResource",
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:rds!db-*"
      },
      {
        Sid    = "ManageStagingEncryptionGrants"
        Effect = "Allow"
        Action = [
          "kms:CreateGrant",
          "kms:DescribeKey",
          "kms:ListGrants",
          "kms:RevokeGrant",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = var.aws_region
          }
        }
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "staging_storage_and_secrets" {
  role       = aws_iam_role.github_deploy.id
  policy_arn = aws_iam_policy.staging_storage_and_secrets.arn
}
