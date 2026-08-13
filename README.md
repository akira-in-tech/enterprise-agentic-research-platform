<p align="center">
  <img src="frontend/src/assets/evident-mark.png" alt="Evident logo" width="76" height="76">
</p>

<h1 align="center">Evident</h1>

<p align="center"><strong>Deep research you can inspect, resume, and trust.</strong></p>

<p align="center">
  Evident turns complex questions into conclusion-first reports backed by
  traceable web, academic, and private evidence.
</p>

<p align="center">
  <a href="#product-experience">Product</a> ·
  <a href="#how-evident-researches">8-Agent Workflow</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#run-it-locally">Run Locally</a> ·
  <a href="#engineering-quality">Quality</a>
</p>

---

Evident is a general-purpose, multi-tenant research platform for technical,
business, policy, market, and internal-knowledge questions. It combines an
eight-agent LangGraph workflow with durable execution, source-level evidence
inspection, private RAG, and explicit model selection.

The goal is not to produce the most confident-sounding answer. It is to make
the path from question to conclusion visible and auditable.

## Product experience

<p align="center">
  <img src="frontend/artifacts/demo/06-report-completed.png" alt="Evident completed research report with inline citations and research quality summary" width="92%">
</p>

The interface follows a deliberate information hierarchy:

1. **Read the conclusion first.** The report remains the primary surface.
2. **Check research quality next.** Citation coverage, source mix, conflicts,
   and review status are visible without reading internal traces.
3. **Open evidence when needed.** The evidence panel stays out of the reading
   path until a citation or source deserves inspection.

| Product promise                  | What the user gets                                                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Evidence over assertions         | Inline citations resolve to the exact scored source pool used by the workflow.                                                        |
| Private knowledge, safely scoped | Uploaded TXT, Markdown, and PDF documents are isolated by tenant and can be selected per research run.                                |
| Provider control                 | Choose Claude or local Qwen per request; the choice is persisted with the run for auditability.                                       |
| Durable work                     | Queued jobs, agent steps, checkpoints, leases, reports, sources, and audit events survive process restarts.                           |
| Honest uncertainty               | Conflicts, unsupported claims, evidence gaps, high-risk domains, and citation-revision requirements are first-class states.           |
| Inspectable cost and quality     | The evaluation harness records quality, latency, token usage, and explicitly configured provider cost without inventing missing data. |

### Two real end-to-end demos

The primary demo was recorded against the AWS staging deployment, using Claude
and the full research workflow for: _“Compare HTTP/2 and HTTP/3 using current
technical sources.”_

<p>
  <img src="frontend/artifacts/demo/03-composer-filled.png" alt="Research composer with provider selection and the eight-agent workflow preview" width="49%">
  <img src="frontend/artifacts/demo/05-agent-workflow-in-progress.png" alt="Live eight-agent research workflow progress" width="49%">
</p>
<p>
  <img src="frontend/artifacts/demo/06-report-completed.png" alt="Completed report with inline citations" width="49%">
  <img src="frontend/artifacts/demo/07-evidence-expanded.png" alt="Expanded evidence panel with citation coverage and source verification" width="49%">
</p>

Watch the [full research recording](frontend/artifacts/demo/demo.mp4).

The Private Knowledge demo exercises the path public-search demos usually
skip: upload a document, embed and index it through the real Bedrock Titan V2
and Milvus pipeline, scope a run to that document, and verify that the final
report cites the private source instead of confusing it with unrelated public
results.

<p>
  <img src="frontend/artifacts/demo/private-knowledge/04-composer-scoped-to-private-doc.png" alt="Research composer scoped to a selected private document" width="49%">
  <img src="frontend/artifacts/demo/private-knowledge/08-evidence-with-private-source.png" alt="Evidence panel identifying and verifying a private source" width="49%">
</p>

Watch the [Private Knowledge recording](frontend/artifacts/demo/private-knowledge/demo.mp4).

The staging URL is
[d5llhn72jopyp.cloudfront.net](https://d5llhn72jopyp.cloudfront.net) when the
stack is active. Staging is intentionally **demo-on-demand**, so the URL may be
offline between review sessions to avoid idle cloud cost.

## How Evident researches

Simple questions take a fast direct-answer path. Questions requiring current,
comparative, multi-source, or private evidence enter the canonical eight-agent
workflow.

```text
1. Intent Router
   ├── direct → Direct Answer
   └── deep research
        ↓
2. Planner
        ↓
3. Web Scout  ─────┐
4. Local Scout ────┴─ run in parallel
        ↓
5. Evidence Judge
        ↓
6. Analyst
        ↓
7. Reflect ── evidence gap + budget → targeted scout round
        ↓
8. Writer ─── citation validation and bounded repair → Report
```

| Agent          | Responsibility                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------- |
| Intent Router  | Chooses direct answer or deep research and flags high-risk domains.                               |
| Planner        | Decomposes the request into research tasks and a domain-appropriate report outline.               |
| Web Scout      | Retrieves public web, academic, and optional MCP evidence.                                        |
| Local Scout    | Searches only the tenant's permitted private-document scope.                                      |
| Evidence Judge | Normalizes, scores, deduplicates, and identifies gaps or conflicts.                               |
| Analyst        | Converts evidence into structured findings tied to canonical source IDs.                          |
| Reflect        | Applies the quality gate and can request one bounded supplementary round.                         |
| Writer         | Produces a conclusion-first report and repairs invalid citation references within a fixed budget. |

All agents communicate through `ResearchState`; durable jobs additionally
persist node-level checkpoints and agent-step traces. See
[docs/workflow.md](docs/workflow.md) for routing, state fields, and recovery
semantics.

## Trust is a runtime feature

The console is designed for failure and ambiguity, not only the happy path.

| State                      | Product behavior                                                                                                                                                                    |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Redis unavailable          | Result-cache and progress publishing degrade without losing durable PostgreSQL work. Idempotency and rate limiting fail closed with `503` when their guarantees cannot be enforced. |
| SSE disconnected           | The UI announces the lost live connection; the durable job may continue and its state can be rehydrated from the API.                                                               |
| Job failed                 | The run keeps an explicit terminal state, bounded error detail, checkpoints, and audit history.                                                                                     |
| Report unavailable         | The user sees a deliberate unavailable state rather than an empty report surface.                                                                                                   |
| Citation revision required | The report remains visible with a first-class quality warning instead of being presented as verified.                                                                               |
| High-risk domain           | Medical, legal, financial, and safety-critical research requires human review independently of citation coverage.                                                                   |
| Cancellation requested     | Only queued or running jobs transition to cancelled; late cancellation cannot rewrite a completed result.                                                                           |

This separation is intentional: PostgreSQL is the source of truth, while Redis
is used only where its speed or coordination semantics add value.

## Architecture

```mermaid
flowchart TB
    user["Researcher"] --> ui["Vue 3 + Vite console"]
    ui -->|"REST + SSE"| api["FastAPI application"]
    api --> auth["Session auth + tenant boundary"]
    api --> jobs["Durable job manager"]
    jobs --> graph["LangGraph 8-agent workflow"]

    graph --> llm["Claude / Qwen"]
    graph --> public["Tavily + Semantic Scholar"]
    graph --> mcp["MCP tools"]
    graph --> private["Private RAG"]
    private --> embed["Ollama / Bedrock embeddings"]
    embed --> milvus["Milvus / Zilliz Cloud"]

    api <--> postgres["PostgreSQL\nruns, reports, sources, checkpoints, audit"]
    api <--> redis["Redis / Valkey\ncache, idempotency, locks, rate limits, progress"]
    api --> objects["Local storage / private S3\ndocuments and report exports"]
```

### State and provider boundaries

| Boundary       | Implementations                                                                 |
| -------------- | ------------------------------------------------------------------------------- |
| LLM            | Claude through Anthropic; Qwen through Ollama                                   |
| Search         | Tavily web search; Semantic Scholar academic search; optional MCP federation    |
| Embeddings     | Qwen embeddings through Ollama; Amazon Titan Text Embeddings V2 through Bedrock |
| Vector store   | In-memory test store; Milvus / Zilliz Cloud                                     |
| Object storage | Private local filesystem; private Amazon S3                                     |
| Durable state  | PostgreSQL with SQLAlchemy, Alembic, and LangGraph's PostgreSQL checkpointer    |
| Coordination   | Redis locally; Amazon ElastiCache for Valkey in AWS staging                     |

For the detailed component and request-flow diagrams, see
[docs/architecture.md](docs/architecture.md). For the schema and ERD, see
[docs/data-model.md](docs/data-model.md).

## Product surface

- Authenticated tenant registration, login, profile, password change, and
  session logout.
- Synchronous research and durable asynchronous jobs with polling and SSE.
- Run history, progress, cancellation, report retrieval, scored sources, and
  Markdown/PDF export with numbered or footnote citations.
- Private Knowledge upload, list, detail, retry, selection, and deletion.
- Provider capability and readiness endpoints.
- MCP Streamable HTTP server for web search, private retrieval, source lookup,
  document ingestion, report persistence, history, and human-review requests.

Every research endpoint derives tenant and user identity from an authenticated
session. Client-supplied identity headers are not trusted. See
[docs/security.md](docs/security.md) for the implemented boundary and the
remaining account-management limitations.

## Run it locally

### Docker Compose

The shortest path starts the complete local stack:

```bash
cp .env.example .env
docker compose up --build --detach --wait
```

Open [http://localhost:3000](http://localhost:3000). The Compose topology and
smoke test are documented in [docs/deployment.md](docs/deployment.md#local).

### Python and Node development

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

PDF rendering uses WeasyPrint and native Pango libraries. On macOS:

```bash
brew install weasyprint
export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
python -m weasyprint --info
```

### First research request

```bash
curl -c cookies.txt -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"researcher@example.com","password":"correct-horse-battery","tenant_name":"Example Research"}'

curl -b cookies.txt -X POST http://127.0.0.1:8000/research-runs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: first-research-request' \
  -d '{"query":"Compare PostgreSQL logical replication and change data capture.","llm_provider":"qwen"}'
```

Use `POST /research-runs/jobs` for durable asynchronous execution. The response
returns the run, progress, events, and report URLs.

## Engineering quality

Default tests are deterministic and do not call paid or external services.
Live integrations are explicit and opt-in.

```bash
ruff check .
mypy app tests scripts alembic/env.py alembic/versions
pytest -q
```

The Docker test target includes the native Linux PDF dependencies used by the
application image and CI:

```bash
docker build --target test --tag evident-backend-test .
docker run --rm evident-backend-test
```

```bash
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npx playwright test
```

The verification strategy covers unit tests, API contracts, PostgreSQL and
Redis integration, live provider smoke tests, reversible migrations, restart
recovery, Playwright user journeys, Terraform validation, container packaging,
and reproducible research evaluation. Current verified counts and known gaps
live in [docs/status.md](docs/status.md); evaluation fixtures and published runs
live in [docs/evaluation.md](docs/evaluation.md).

## Deployment

Terraform defines the AWS staging stack: CloudFront, an Application Load
Balancer, ECS Fargate, RDS PostgreSQL, ElastiCache for Valkey, private S3,
Bedrock access, ECR, and GitHub OIDC deployment identity.

The stack has been applied and verified with a real public research run and a
separate private-document Bedrock/Milvus round trip. It is operated on demand
because the running resources incur cost.

```bash
# Deploy after configuring the Terraform backend and required secrets.
TF_VAR_budget_notification_email=you@example.com \
TF_VAR_anthropic_model=replace-with-supported-model-id \
TF_VAR_milvus_uri=https://replace-with-managed-milvus-endpoint \
ANTHROPIC_API_KEY=... TAVILY_API_KEY=... MILVUS_TOKEN=... \
scripts/aws-deploy.sh

# Destroy billable staging resources; the protected state bucket remains.
AWS_DESTROY_CONFIRM=destroy-staging scripts/aws-destroy.sh
```

Review the cost basis, networking, secret flow, and deployment lifecycle in
[docs/deployment.md](docs/deployment.md#aws-staging) before applying.

## Documentation

| Document                                   | Purpose                                                                  |
| ------------------------------------------ | ------------------------------------------------------------------------ |
| [Project charter](docs/PROJECT_CHARTER.md) | Product vision, scope, phases, and final acceptance criteria             |
| [Architecture](docs/architecture.md)       | Components, provider boundaries, and request flows                       |
| [Research workflow](docs/workflow.md)      | Eight agents, routing, shared state, and durable execution               |
| [Data model](docs/data-model.md)           | PostgreSQL schema and ERD                                                |
| [Security](docs/security.md)               | Authentication, tenant isolation, prompt-injection handling, and secrets |
| [Reliability](docs/reliability.md)         | Retry, circuit breaking, checkpoint recovery, and failure isolation      |
| [Evaluation](docs/evaluation.md)           | Metrics, fixtures, published runs, limitations, and cost methodology     |
| [Trade-offs](docs/trade-offs.md)           | Architectural decisions and rejected alternatives                        |
| [Deployment](docs/deployment.md)           | Local topology, CI/CD, AWS staging, and cost controls                    |
| [Status](docs/status.md)                   | Evidence-backed implementation and verification log                      |

## Design principles

- Put the conclusion first, research quality second, and evidence on demand.
- Make provider choice, private scope, and human-review state explicit.
- Treat tenant isolation, idempotency, and durable ownership as correctness
  boundaries rather than UI details.
- Keep paid integrations opt-in and record only reproducible metrics.
- Keep provider SDKs behind application interfaces so the product is not tied
  to one model, search engine, vector store, or cloud runtime.
- Never present planned, mocked, local-only, or unavailable behavior as a
  verified production capability.
