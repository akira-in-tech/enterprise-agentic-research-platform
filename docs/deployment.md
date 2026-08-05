# Deployment

## Local

`docker compose up --build --detach --wait` starts eight healthy services
(FastAPI, Vue/Nginx, PostgreSQL, Redis, Milvus, etcd, MinIO, and the MCP
server). See the root README's "Local Docker Compose Stack" section for
the exact command sequence, port topology, and the repeatable
`scripts/compose-smoke.sh` verification.

## AWS staging

Terraform is split into three roots (`infra/terraform/`):

- `bootstrap` — the protected, encrypted, versioned remote-state S3 bucket.
  **Applied and AWS-verified.**
- `identity` — GitHub OIDC deployment identity with exact repository/
  environment trust. **Applied and AWS-verified.**
- `staging` — VPC, ECR, RDS PostgreSQL, ElastiCache/Valkey, S3 document
  storage, ARM64 ECS Fargate, ALB, CloudFront, budget alerts.
  **Terraform-validated and mock-tested; not yet applied.**

As of this writing, only the state bucket and the CI deployment identity
are live AWS resources. The application stack (ECS task, RDS, Valkey, ALB,
CloudFront) has never been `terraform apply`'d — deploying it is a
deliberate, explicit action (`scripts/aws-deploy.sh` or the `Deploy AWS
staging` GitHub Actions workflow), not something this repository does
automatically. See the root README's "AWS Staging Deployment" section for
the full cost breakdown and the demo-on-demand operating model (apply for
an active review, verify, then `scripts/aws-destroy.sh`).

## CI/CD

Four GitHub Actions jobs gate every PR and push to `main`
(`.github/workflows/ci.yml`): backend quality (Ruff, mypy, pytest),
frontend quality (typecheck, Vitest, build), a PostgreSQL+Redis
`integration` job running the subset of `@pytest.mark.integration` tests
that need only those two services, and Terraform quality. Container
packaging depends on all four passing before building images. A separate
`deploy-aws.yml` workflow performs an actual staging deploy through a
protected GitHub environment and AWS OIDC, invoked manually — it is not
part of the default PR gate.
