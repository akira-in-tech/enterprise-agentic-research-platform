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
