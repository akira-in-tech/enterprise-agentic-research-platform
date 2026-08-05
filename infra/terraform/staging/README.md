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
       ├── private S3 document source objects
       ├── Amazon Bedrock Titan V2 embeddings
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
- private, encrypted, versioned S3 document storage with public access blocked
- least-privilege task permissions for the document bucket and Titan embeddings
- one ARM64 Fargate task containing the FastAPI and Nginx/Vue containers
- an ALB restricted to the AWS-managed CloudFront origin network
- a CloudFront HTTPS endpoint with caching disabled for `/api/*`
- seven-day CloudWatch log retention and ECS deployment rollback

No infrastructure is created by repository tests or `terraform validate`.
Creating AWS resources requires an explicit `terraform apply`.

## Operating model

This environment is demo-on-demand rather than an always-on production stack.
Deploy it for an active review or interview session, complete the smoke test,
and run the guarded destroy workflow afterward. Setting
`application_desired_count = 0` stops Fargate task charges but does not stop
charges for RDS, ElastiCache, the ALB, public IPv4 addresses, Secrets Manager,
or stored images. Routine destruction preserves the separate protected S3
Terraform state bucket.

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

## Verified remote plan and cost boundary

The protected GitHub Actions OIDC job generated a real remote-state-backed plan
on 2026-08-02 with `application_desired_count = 0`, before the private S3 and
Bedrock resources were added:

```text
Plan: 48 to add, 0 to change, 0 to destroy.
```

That count is now historical and must not be used to approve an apply. Generate
a fresh authenticated plan first. No Terraform plan artifact is uploaded because
plan files can contain sensitive values. The job emits only deterministic
change counts to its step summary.

The following fixed-cost estimate uses 730 hours per month and public
`us-west-2` on-demand rates from the AWS Price List. It excludes traffic-driven
ALB LCUs, CloudFront and internet transfer, CloudWatch ingestion, ECR storage,
Secrets Manager API calls, external providers, and taxes.

| Planned component | Estimated monthly cost |
| --- | ---: |
| RDS PostgreSQL `db.t4g.micro` | $11.68 |
| RDS gp3 storage, 20 GiB | $2.30 |
| ElastiCache Valkey `cache.t4g.micro` | $9.34 |
| Application Load Balancer | $16.42 |
| Two public IPv4 addresses | $7.30 |
| Three Secrets Manager secrets | $1.20 |
| Zero-task fixed baseline | **$48.25** |
| One 0.5 vCPU / 1 GiB ARM64 Fargate task | +$14.42 |
| Public IPv4 address assigned to the running task | +$3.65 |
| One-task fixed baseline | **$66.32** |

A four-hour demo with one task is approximately $0.36 before variable usage;
a 24-hour demo is approximately $2.18. These are estimates, not billing caps.
The configured $25 monthly budget sends alerts but does not stop resources.
Current rates should be rechecked before every apply against the official
[RDS](https://aws.amazon.com/rds/postgresql/pricing/),
[ElastiCache](https://aws.amazon.com/elasticache/pricing/),
[Elastic Load Balancing](https://aws.amazon.com/elasticloadbalancing/pricing/),
[VPC IPv4](https://aws.amazon.com/vpc/pricing/), and
[Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/) pages.

The plan still contains non-deployable placeholder values for the Anthropic
model and managed Milvus endpoint. Configure those values and the three
provider credentials before approving an application deployment. Creating the
zero-task infrastructure before those inputs exist would incur the fixed
baseline without producing a usable demo.

The RDS password is generated and stored through the RDS-managed Secrets
Manager integration. The cache token is randomly generated and stored in the
encrypted remote Terraform state. Deployment automation pipes that token and
the required environment-provided provider credentials directly into their
Secrets Manager records without reading existing secret values or exposing
secret strings as command arguments. Never commit a plan file because
Terraform plans can contain sensitive values.

The first full apply keeps `application_desired_count = 0`, so AWS can create
the ECR repositories and dependencies before images exist. Push both ARM64
images under the same immutable Git SHA, set both image-tag variables to that
SHA, update the external provider secret, and then set
`application_desired_count = 1`.

## Repeatable deployment

The deployment script performs the dependency-first apply, writes the cache
and provider secrets from in-memory values, pushes both Linux ARM64 images
under one immutable Git SHA, starts the service, waits for ECS stability,
invalidates CloudFront, and verifies `/api/health`.

It fails before Terraform initialization when any required deployment input is
missing or when the Anthropic model or Milvus endpoint still contains a
documented placeholder. Error output names missing variables but never prints
their values.

Example:

```bash
TF_VAR_budget_notification_email=you@example.com \
TF_VAR_anthropic_model=replace-with-supported-model-id \
TF_VAR_milvus_uri=https://replace-with-managed-milvus-endpoint \
ANTHROPIC_API_KEY=... \
TAVILY_API_KEY=... \
MILVUS_TOKEN=... \
scripts/aws-deploy.sh
```

GitHub Actions exposes the same operation as the manually dispatched
`Deploy AWS staging` workflow. Configure a protected `staging` environment
with repository variables `AWS_REGION`, `TF_STATE_BUCKET`,
`AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`, `BUDGET_NOTIFICATION_EMAIL`,
`ANTHROPIC_MODEL`, and `MILVUS_URI`; configure environment secrets
`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, and `MILVUS_TOKEN`. The AWS role must
trust GitHub OIDC for this repository and environment. Long-lived AWS access
keys are not used.

Destroy the billable staging stack explicitly:

```bash
AWS_DESTROY_CONFIRM=destroy-staging scripts/aws-destroy.sh
```

The destroy script produces and applies a dedicated destroy plan. The separate
versioned state bucket remains protected and must not be removed during routine
staging cleanup.
