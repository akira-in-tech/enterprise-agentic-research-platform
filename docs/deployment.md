# Deployment

## Local

The complete local stack is reproducible from the repository:

```bash
cp .env.example .env
# Add provider credentials when needed, then start the stack.
docker compose up --build --detach --wait
```

This starts eight healthy services: FastAPI, Vue/Nginx, PostgreSQL, Redis,
Milvus, etcd, MinIO, and the MCP server. Open `http://localhost:3000` — the
frontend Nginx service proxies `/api` to the FastAPI container, including
unbuffered SSE responses, and the API runs Alembic to the current head
before Uvicorn starts.

```text
browser
→ Nginx and Vue frontend
→ FastAPI and Alembic
→ PostgreSQL + Redis + Milvus
                 → etcd + MinIO
→ host Ollama through host.docker.internal when Qwen is selected
```

PostgreSQL, Redis, Milvus, etcd, and MinIO are not published to the host by
default — only the frontend and API bind to loopback, which avoids exposing
state services and prevents conflicts with separately managed
integration-test containers.

Run the repeatable isolated smoke check on temporary host ports:

```bash
./scripts/compose-smoke.sh
```

The script validates the Compose configuration, builds both application
images, waits for all eight services to become healthy, calls the API
through Nginx, checks the Alembic head and Redis, validates Nginx, and
stops the containers. Named development volumes persist across runs; stop
a manually started stack without deleting them via `docker compose down`.

## AWS staging

```text
browser
→ CloudFront HTTPS and static-asset cache
→ CloudFront-only Application Load Balancer ingress
→ one ARM64 ECS Fargate task
   ├── Nginx + Vue frontend
   └── FastAPI + Alembic
       ├── private encrypted RDS PostgreSQL
       ├── private encrypted ElastiCache for Valkey
       ├── Secrets Manager provider credentials
       ├── private encrypted and versioned S3 source objects
       ├── external managed Milvus-compatible endpoint
       └── Claude + Tavily + Bedrock over controlled outbound access
```

The topology deliberately omits a NAT Gateway: Fargate tasks receive
explicit public egress addresses in public subnets but accept application
traffic only from the load balancer, while RDS and Valkey stay in isolated
data subnets accepting traffic only from the application security group.
CloudFront provides the first HTTPS endpoint; a custom domain and
certificate are not yet configured. The cloud image enables Claude only,
since the cost-controlled Fargate task does not run Ollama — local builds
continue to expose both Claude and Qwen. AWS staging selects Titan Text
Embeddings V2 through Bedrock and a private S3 bucket for source objects;
both adapters and the Terraform contract are locally verified, but no live
Bedrock invocation or application apply is claimed yet.

Terraform is split into three roots (`infra/terraform/`):

- `bootstrap` — the protected, encrypted, versioned remote-state S3 bucket.
  **Applied and AWS-verified.**
- `identity` — GitHub OIDC deployment identity with exact repository/
  environment trust. **Applied and AWS-verified.**
- `staging` — two-AZ VPC, immutable ECR, single-AZ RDS PostgreSQL,
  single-node Valkey, Secrets Manager credentials, private S3 document
  storage, least-privilege ECS task access, ARM64 Fargate, ALB,
  CloudFront, and monthly budget alerts.
  **Terraform-validated and mock-tested; not yet applied.**

As of this writing, only the state bucket and the CI deployment identity
are live AWS resources. The application stack (ECS task, RDS, Valkey, ALB,
CloudFront) has never been `terraform apply`'d — deploying it is a
deliberate, explicit action (`scripts/aws-deploy.sh` or the `Deploy AWS
staging` GitHub Actions workflow), not something this repository does
automatically.

The staging defaults prioritize cost control, not high availability: zero
running application tasks until images exist, 0.5 vCPU / 1 GiB per running
task, small Graviton database/cache instances, seven-day logs, twenty
retained images per repository, no NAT Gateway, and a USD 25 monthly
budget alert (an alert, not a spending cap — RDS, Valkey, the ALB,
CloudFront, Secrets Manager, ECR, and Fargate can all incur cost after
apply, even at zero desired task count). At public `us-west-2` rates
checked on 2026-08-02, the planned zero-task stack has an estimated fixed
baseline of about $48.25 per 730-hour month; one running 0.5 vCPU / 1 GiB
ARM64 Fargate task plus its assigned public IPv4 address raises that to
about $66.32 before traffic, logs, image storage, provider APIs, and
taxes.

The operating model is demo-on-demand: apply the full stack only for an
active review or interview session, verify the public endpoint, then
destroy it. Scaling ECS to zero is not sufficient — RDS, Valkey, the ALB,
public IPv4 addresses, and secrets keep incurring charges. The protected
state bucket intentionally survives routine staging destruction.

Deploy locally, after configuring the staging backend file and supplying
the required provider variables and secrets:

```bash
TF_VAR_budget_notification_email=you@example.com \
TF_VAR_anthropic_model=replace-with-supported-model-id \
TF_VAR_milvus_uri=https://replace-with-managed-milvus-endpoint \
ANTHROPIC_API_KEY=... \
TAVILY_API_KEY=... \
MILVUS_TOKEN=... \
scripts/aws-deploy.sh
```

The script applies dependencies with zero tasks, writes cache and provider
credentials to Secrets Manager, pushes both Linux ARM64 images under one
immutable Git SHA, starts the service, waits for ECS stability, invalidates
CloudFront, and verifies `/api/health`. It rejects missing deployment
inputs and documented placeholder values before Terraform initialization,
without printing secrets. The manual `Deploy AWS staging` GitHub Actions
workflow performs the same operation through a protected environment and
AWS OIDC, without long-lived AWS keys.

Destroy billable staging resources only after reviewing the active account
and the generated plan:

```bash
AWS_DESTROY_CONFIRM=destroy-staging scripts/aws-destroy.sh
```

The separate versioned state bucket remains protected during routine
staging destruction. Full variables, bootstrap steps, GitHub environment
configuration, and failure recovery are documented in
`infra/terraform/staging/README.md`.

## CI/CD

Four GitHub Actions jobs gate every PR and push to `main`
(`.github/workflows/ci.yml`):

```text
Backend quality
→ install Python 3.13 dependencies
→ Ruff
→ strict mypy
→ default pytest suite without live integrations

Frontend quality
→ reproducible npm ci install on Node.js 22
→ dependency audit
→ Vue and TypeScript typecheck
→ Vitest
→ Playwright end-to-end suite
→ Vite production build

PostgreSQL + Redis integration
→ start postgres:17-alpine and redis:8-alpine service containers
→ run the subset of @pytest.mark.integration tests that need only those
  two services (durability, idempotency, rate limiting, progress,
  cancellation, agent-step tracing, and live API round trips)

Terraform quality
→ recursive formatting check
→ bootstrap and staging initialization without remote state
→ Terraform validation and mock plan-invariant test
→ deployment and destroy script syntax checks

Container packaging
→ validate Compose configuration and smoke-script syntax
→ build the FastAPI image
→ build the Vue and Nginx image
```

Container packaging depends on the other four jobs passing. The
eight-service Compose smoke test remains an explicit local/manual check
rather than a default PR gate — starting Milvus, etcd, and MinIO on every
pull request would add substantial latency for a check that container
packaging already partially covers by building both images. A separate
`deploy-aws.yml` workflow performs an actual staging deploy through a
protected GitHub environment and AWS OIDC, invoked manually — it is not
part of the default PR gate.
