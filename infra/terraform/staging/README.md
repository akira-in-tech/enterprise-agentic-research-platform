# AWS Staging Environment

This stack defines a cost-controlled, disposable AWS staging environment for
the Evident research platform.

The network deliberately has no NAT Gateway. The application task will run in
public subnets with an assigned public IP for outbound Anthropic, Tavily, and
managed Milvus access. Its security group accepts inbound traffic only from the
load balancer. PostgreSQL and Redis remain in isolated data subnets without a
default internet route.

```text
Internet
→ CloudFront HTTPS (compute step)
→ public ALB
→ public-subnet ECS Fargate task with public egress
   ├── frontend Nginx container
   └── FastAPI container
       ├── isolated-subnet RDS PostgreSQL
       ├── isolated-subnet ElastiCache
       └── external Anthropic, Tavily, and managed Milvus endpoints
```

The first infrastructure increment includes:

- a two-AZ VPC
- public ingress/task subnets and isolated data subnets
- no NAT Gateway
- security-group-to-security-group database and cache access
- immutable, encrypted, scan-on-push ECR repositories
- image retention capped at 20 versions
- forecasted 80% and actual 100% monthly budget notifications
- private single-AZ RDS PostgreSQL with encrypted gp3 storage
- private single-node Valkey-compatible ElastiCache with TLS and encryption
- AWS-managed RDS credentials and Secrets Manager provider credentials

No infrastructure is created by repository tests or `terraform validate`.
Creating AWS resources requires an explicit `terraform apply`.

## Local validation

Create the shared state bucket first, then copy the examples without committing
the local files:

```bash
cp infra/terraform/bootstrap/backend.hcl.example \
  infra/terraform/bootstrap/backend.hcl
cp infra/terraform/staging/terraform.tfvars.example \
  infra/terraform/staging/terraform.tfvars

cd infra/terraform/staging
terraform init -backend-config=../bootstrap/backend.hcl
terraform fmt -check
terraform validate
terraform plan -out staging.tfplan
```

An authenticated plan contacts AWS to resolve account and availability-zone
data but does not create resources. Review the plan and the AWS Pricing
Calculator before applying it.

After the first apply, replace the external-provider placeholders without
putting credentials in Terraform variables or Git:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw provider_secret_arn)" \
  --secret-string '{
    "ANTHROPIC_API_KEY":"replace-me",
    "TAVILY_API_KEY":"replace-me",
    "MILVUS_TOKEN":"replace-me"
  }'
```

The RDS password is generated and stored through the RDS-managed Secrets
Manager integration. The cache token is randomly generated and stored in the
encrypted remote Terraform state as well as Secrets Manager. Never commit a
plan file because Terraform plans can contain sensitive values.
