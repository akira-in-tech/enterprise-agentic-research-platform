# Project Status

This is the detailed, continuously-updated engineering status log: a
component-by-component verification table, a chronological build log, the
current architecture with per-component deployment/verification status
annotated, and the latest verified test-run snapshots. Read
[README.md](../README.md) first for what the platform is and how to run it;
come here for exactly what has been built, tested, and verified so far, and
what has not.

## Component Status

| Component | Status |
| --- | --- |
| FastAPI application and health endpoint | Tested |
| Provider-neutral LLM interface | Tested |
| Claude provider | Tested with mocks |
| Qwen LLM provider through Ollama | Tested with mocks and live integration test |
| Domain-neutral intent router with deterministic fallback | Tested |
| Domain-neutral direct-answer agent | Tested |
| Domain-neutral structured research planner | Tested |
| Canonical eight-agent LangGraph workflow | Tested with deterministic graph and factory tests |
| Intent Router direct/deep branch | Tested |
| Planner structured research tasks | Tested |
| Parallel Web Scout and tenant-scoped Local Scout fan-out | Tested |
| Evidence Judge normalization, gaps, and conflicts | Tested |
| Analyst structured findings | Tested |
| Bounded Reflect supplementary-research loop | Tested |
| Independent Writer and bounded citation repair | Tested |
| Tavily search provider | Tested with mocks and live smoke test |
| Bounded concurrent search executor | Tested |
| Per-task search timeout and failure isolation | Tested |
| URL normalization and stable web source IDs | Tested |
| TXT and Markdown private-document parsing | Tested |
| PDF text extraction | Tested |
| Deterministic document chunking | Tested |
| Durable tenant-scoped private-document metadata and indexing lifecycle | Tested with repository coverage and a reversible live PostgreSQL migration |
| Private source object storage | Local filesystem and private S3 providers tested; AWS bucket is Terraform-declared with encryption, versioning, lifecycle cleanup, and all public access blocked |
| Tenant-scoped document REST API | Upload, list, detail, and delete paths tested with multipart limits and explicit duplicate, indexing, storage, and not-found states |
| End-to-end private-document lifecycle | Live PostgreSQL upload, deterministic indexing, semantic retrieval, source deletion, vector deletion, and metadata cleanup verified |
| Vue Private Knowledge console | Typechecked, component tested, and production built with upload, empty, loading, failed, ready, deleting, retry, and two-step deletion states |
| Provider-neutral embedding interface | Tested |
| Qwen embeddings through Ollama | Tested with mocks and live smoke test |
| Amazon Bedrock Titan V2 embeddings | Provider, request/response validation, retry configuration, lifecycle cleanup, and provider selection unit tested; live AWS invocation pending |
| Provider-neutral vector-store interface | Tested |
| In-memory vector store | Tested |
| Milvus collection initialization | Tested |
| Milvus vector upsert, search, and deletion | Tested with unit and live integration tests against local Milvus and managed Zilliz Cloud in AWS us-west-2 |
| Tenant-scoped private knowledge retrieval | Tested |
| Per-request private-document scoping | Optional `document_ids` narrows retrieval to specific tenant documents end-to-end (vector store, retriever, Local Scout, workflow state/graph, result cache key, idempotency fingerprint, execution/job services, API validation, Vue picker); unit tested at every layer plus a live deep-research run verifying isolation between two private documents |
| Canonical private source generation | Tested |
| Ollama-to-Milvus private RAG pipeline | Live integration tested |
| Vector-store provider factory | Tested |
| Per-request Claude/Qwen user selection | Tested |
| Claude structured-output provider | Live integration tested with `claude-sonnet-5` |
| Async PostgreSQL engine and session factory | Tested |
| Alembic migration environment | Tested |
| Tenant, user, and research-run schema | Tested with reversible live migration |
| Tenant-scoped PostgreSQL repositories | Tested with unit and live integration tests |
| Atomic research-run lifecycle transitions | Tested |
| Durable research execution service | Tested |
| Tenant-scoped research REST endpoint | Tested with unit and live integration tests |
| Async Redis connection pool and health check | Tested with unit and live integration tests |
| Tenant/provider/query-scoped Redis cache keys | Tested |
| Redis research-result serialization and TTL | Tested with unit and live integration tests |
| Research execution cache miss, write, and hit paths | Tested with unit and live integration tests |
| Redis fail-open behavior for research execution | Tested |
| FastAPI Redis lifecycle wiring and cleanup | Tested |
| Tenant-scoped Redis idempotency records and request fingerprints | Tested with unit and live integration tests |
| Atomic Redis coordination locks with TTL and token-checked release | Tested with unit and live integration tests |
| Concurrent idempotent research execution and completed-response replay | Tested with unit and live integration tests |
| Research idempotency API conflict and availability handling | Tested |
| Tenant-scoped Redis research rate limiting | Tested with unit and live integration tests |
| Research API rate-limit headers and HTTP 429/503 handling | Tested |
| Tenant-scoped Redis research progress snapshots and TTL | Tested with unit and live integration tests |
| Research execution lifecycle progress publishing | Tested with unit and live integration tests |
| Tenant-scoped research progress REST endpoint | Tested |
| MCP Streamable HTTP tools client | Contract tested with deterministic transport and live verified against the repository's official-SDK server over TCP |
| MCP reference server and research federation | Official Python SDK server, tool discovery/call, fail-open Web Scout federation, Compose service, and AWS sidecar configuration tested |
| Web, private, and MCP evidence normalization | Tested |
| Explainable evidence scoring and citation validation | Tested |
| Analyst report generation and reflection quality gate | Tested |
| Deep-research evidence-quality LangGraph path | Tested |
| Citation and reflection API/cache visibility | Tested |
| Durable report and evidence-source persistence | Tested with reversible live migration and integration test |
| Tenant-scoped research report retrieval API | Tested |
| Operational REST surface | Document lifecycle, standalone scored sources, provider capabilities, liveness, and fail-closed PostgreSQL/Redis readiness contract tested |
| Durable queued background research jobs | Tested with unit and live integration tests |
| Research checkpoint, audit, and worker-lease schema | SQLAlchemy and Alembic tested; live PostgreSQL upgrade/check/downgrade/restore verified |
| Durable research repository operations | Atomic expired-only lease takeover, owner-token renewal/release, latest checkpoint, and chronological audit trail unit and live PostgreSQL tested |
| Runtime worker ownership | PostgreSQL lease claim, heartbeat renewal, token-checked release, audit events, and queued/completed boundary checkpoints live integration tested |
| Restart recovery and node-level resume | Official AsyncPostgresSaver, startup discovery, tenant/run thread IDs, pending-write-safe node checkpoints, and no-repeat resume live PostgreSQL tested |
| Durable research cancellation | Queued/running-only PostgreSQL transition, local worker interruption, terminal Redis/SSE progress, tenant-scoped REST endpoint, and Vue action tested; migration live applied, verified, and downgraded against local PostgreSQL |
| Bounded reflection revision loop | Tested |
| SSE progress and terminal-state streaming | Tested |
| Vue 3 + TypeScript + Vite frontend | Typechecked, 50 tests passed, 13 Playwright end-to-end tests passed, production built, and desktop/mobile browser QA verified |
| Canonical eight-agent workflow and console role mapping | Backend tested; frontend typechecked, component tested, and built |
| Redis, SSE, job, report, and citation-revision UI states | Component and browser-fixture verified |
| Docker Compose project stack | Built and smoke tested across eight healthy services, including the official-SDK MCP server |
| GitHub Actions | Remote verified across backend, frontend, and container quality gates |
| Terraform state bootstrap | Applied and AWS verified: protected S3 bucket plus five security controls; staging backend initialized |
| Cost-controlled AWS staging infrastructure | Applied and AWS-verified, including private S3 documents and Bedrock task permissions |
| ARM64 ECS application packaging | API and Claude-only frontend builds tested locally |
| GitHub OIDC deployment identity | Applied and AWS verified: exact repository/environment trust, three reviewed inline policies, protected remote state, and zero Terraform drift |
| GitHub OIDC deployment workflow | Remotely verified on GitHub Actions: protected staging environment assumed the expected AWS account and deployment role, then generated the zero-task staging plan with short-lived credentials |
| AWS deployment | Applied and AWS-verified: full application stack live (ECS Fargate, RDS PostgreSQL, ElastiCache Valkey, ALB, CloudFront), public endpoint healthy, a real deep-research run completed end to end and recorded (see the root [README's Demo section](../README.md#demo)). Getting there took nine real deploy attempts across two sessions, each surfacing and fixing a genuinely different bug — four rounds of missing IAM permissions on the GitHub OIDC deploy role (budgets, S3 bucket sub-resources, KMS grants, ELB listener attributes, RDS-managed-secret scoping), one IAM combined-inline-policy-size limit requiring a move to a customer-managed policy, two real application bugs only reachable in the cloud path (a `Literal[int]` Pydantic field that doesn't coerce string env vars, and an asyncpg `ssl` query param that raw psycopg rejects), one QEMU arm64 cross-build crash under GitHub Actions' emulation, and one ECR immutable-tag collision on retry (fixed by making the deploy script idempotent). Bedrock live invocation (the embedding path, exercised only by private-document upload) has not yet been separately observed since the recorded demo run used only public web/academic sources; deployment is demo-on-demand, not always-on, so the stack may have since been destroyed — see [docs/deployment.md](deployment.md#aws-staging) |
| Domain-neutral agent isolation | demo_profiles/engineering/ holds example queries, evaluation cases, a reference report outline, and a private-knowledge manifest, none of it imported by application code; deleting the directory does not change routing, planning, retrieval, or report-writing behavior |
| High-risk domain human review | Intent Router detection and ReflectionAgent human_review_required/reason unit tested; surfaced on the synchronous research-run API response |
| Full MCP research tool set | search_web, search_private_documents, retrieve_source, ingest_document, save_research_report, and get_research_history unit tested against real repositories/services with mocked sessions; request_human_review unit tested against the durability audit-event repository |
| research_agent_steps schema, repository, and live execution wiring | SQLAlchemy and Alembic tested; live PostgreSQL upgrade/downgrade/zero-drift and a live tenant/run/step round trip verified; wired into live workflow execution via LangGraph's astream, unit tested against a real graph (ordering, final-state equivalence, failure attribution) and live-Postgres and real-Ollama integration tested; each step start also publishes to the SSE progress stream (unit tested for the exact published sequence, live browser verified showing the Vue agent-flow diagram advance in real time) |
| Report export storage and REST endpoint | ResearchReportExportService unit tested over the existing local/S3 DocumentStorage interface (including a not-found/other-failure distinction for both backends); tenant-scoped `POST`/`GET /research-runs/{id}/report/export` accept `format` (markdown/pdf) and `citation_style` (numbered/footnote) query params, unit tested with mocked dependencies and live-Postgres/live-filesystem integration tested. Citation markers are rewritten into numbered `[1]` or footnote `[^1]` form with a real-link References/Notes list (unit tested); PDF is rendered via Markdown → HTML → WeasyPrint with a branded stylesheet (unit tested, and the exact rendered bytes visually verified inside the production Docker image, since WeasyPrint's native libraries are not installable on this dev machine's host OS). DownloadOptionsMenu in the Vue console offers all four format/style combinations from the report page (component tested; wired into ResearchDetail.vue) |
| Academic-aware web search (Tavily + Semantic Scholar) | AcademicAwareSearchClient fans out to Tavily and the unauthenticated-by-default Semantic Scholar Academic Graph API concurrently, with independent fail-open per leg and a dedicated circuit breaker around the academic leg so a persistently failing provider adds no latency to every search; `source_type`/`authors`/`year`/`venue` flow through the evidence pipeline end to end (`SearchResult` → `WebSource` → `EvidenceSource` → `ResearchReportSourceResponse`), paper-typed sources get a `+0.10` evidence-scoring bonus, and cross-provider source pooling dedupes by normalized URL, preferring the paper-typed result for a shared URL. Unit tested (result mapping, composite fail-isolation, circuit-breaker tripping, scoring bonus, pool dedup — 40+ dedicated tests); live-network verified — a real Tavily call succeeded while a concurrent real Semantic Scholar call hit its unauthenticated rate limit, and the composite client correctly returned Tavily-only results instead of failing the whole search. A live `PAPER-`-prefixed source inside an actual generated report has not yet been observed end to end (blocked by that same rate limit on this network at verification time); Semantic Scholar also works with an optional `SEMANTIC_SCHOLAR_API_KEY` for a higher limit |
| Per-request correlation IDs | Middleware, log-record injection, and header echo unit tested |
| Circuit breaker | Closed/open/half-open state machine unit tested with a fake clock; wired into the Tavily search executor, the Anthropic client, and the Milvus vector store, each with a dedicated test |
| Exponential backoff with jitter | Full-jitter retry helper unit tested (delay calculation, capping, exhaustion, non-retryable passthrough); wired around Ollama, Tavily, and Milvus search's actual connectivity-level exceptions, each with a dedicated retry test |
| Authentication | Email+password registration and login, Argon2id password hashing, a durable sessions table, httpOnly session-cookie middleware, and self-service tenant signup, replacing the pre-authentication X-Tenant-ID/X-User-ID headers; unit, live-Postgres, and Vue/Playwright tested |
| PostgreSQL/Redis CI integration gate | The Postgres/Redis-only subset of integration tests run against postgres:17-alpine and redis:8-alpine service containers on every pull request and push to main |
| Architecture documentation | docs/PROJECT_CHARTER.md and eight supporting documents, cross-referencing actual code paths and explicitly separating implemented from planned |
| Evaluation harness | scripts/run_evaluation.py scores routing accuracy, source coverage, private-knowledge accuracy, report-section coverage, completion rate, human-review trigger rate, and latency against evaluation_cases.jsonl; scoring/loading unit tested against the real fixture file and a mocked HTTP transport. Six real runs published (2026-08-07). Runs 1-4 (`--provider qwen`, local Ollama, no paid provider) root-caused and fixed evidence-pool noise, added an `ORIGIN` field/instruction for preferring private sources, and enabled Qwen3 thinking mode, but overall pass rate held at 20% throughout. Run 5 (`--provider claude`, first real-cost call, explicit go-ahead) confirmed the private-source instruction works cleanly on a stronger model (private-knowledge accuracy 0%→100%) and surfaced a real crash bug (`AnalystAgent.analyze()` had no fallback for a truncated structured response, unlike `EvidenceJudgeAgent`; fixed and unit tested) plus a routing-prompt gap, but landed on the same 20% pass rate for different reasons — including confirming, on a second independent model, that report-section coverage's exact-heading-substring match was under-crediting genuinely well-structured reports. Run 6 fixed that scoring gate (section coverage is now reported, not a pass/fail veto) and the routing prompt, then re-ran qwen with every underlying rate unchanged: overall pass rate **20%→80%**. A fourth, structurally different fix attempt at the one remaining failure (grouping evidence into a labeled private-vs-web section instead of a flat list) was checked with a cheap single-query call before committing to a full re-run and still produced zero private-source citations — four independent fix attempts across four different mechanisms have now failed to move this qwen3:8b-specific gap, which is about as strong a signal as this harness can give that it's a real model capability ceiling, not a remaining prompt bug. `create_llm_client()` also gained an `ollama_model` override so alternative local models can be compared without changing the server-wide `OLLAMA_MODEL` setting; `deepseek-r1:8b` and `deepseek-r1:14b` were both tried as candidate upgrades and both rejected on real evidence — the 8b model doesn't follow this app's `[WEB-XXXXXXXX]` citation format and drifted off-topic, and the 14b model is too slow on this hardware to finish a multi-step research run at all. Real, published findings throughout, flattering or not — see [evaluation.md](evaluation.md#a-fourth-attempt-at-qwen38bs-private-knowledge-gap-still-unresolved) and [evaluation.md](evaluation.md#trying-alternative-local-models-deepseek-r18b-and-deepseek-r114b) |
| Prompt-injection-aware evidence handling | Web, private-document, and MCP evidence content is delimited and flagged as untrusted data (not instructions) before reaching the Analyst or Writer LLM prompt, with forged-delimiter stripping; unit tested at the helper level and through both agents' prompt construction |
| Open-source contribution | Planned |

Evaluation metrics above come from six real, published runs (see
[evaluation.md](evaluation.md)); there is no deployed application environment
yet. The Terraform state bucket is infrastructure plumbing, not an
application deployment. Local Docker services and mocked providers are not
described as production deployments.

## Development Log

```text
Completed: Phase 0 through Phase 13
Completed: canonical eight-agent backend and console alignment
Implemented and locally validated: Phase 14 AWS staging foundation
Deployed and verified: protected Terraform remote-state bootstrap in us-west-2
Initialized and validated: staging Terraform uses the protected S3 backend
Deployed and verified: immutable-repository GitHub OIDC identity, 5 add / 0 change / 0 destroy
Remotely verified: protected GitHub Actions OIDC role assumption with short-lived credentials
Previously remotely verified: zero-task staging plan before the private-knowledge AWS provider slice
Configured and live verified: Claude Sonnet 5 structured output through the Anthropic API
Configured and live verified: managed Zilliz Cloud Milvus round trip in AWS us-west-2
Configured and live verified: Tavily Basic Search and canonical web-source normalization
Completed and verified: complete Private Knowledge upload product flow
Implemented and live verified: tenant-scoped document upload, list, detail, delete, source storage, indexing, retrieval, and lifecycle persistence
Implemented and verified: Vue Private Knowledge upload, lifecycle, recovery, and deletion console
Implemented and locally verified: Amazon Bedrock Titan V2 embeddings and private S3 source-object storage
Terraform validated and mock tested: encrypted, versioned, public-blocked S3 plus least-privilege ECS task access
Deployment status: state bucket and CI identity only; staging application resources are not applied
Implemented and live verified: official SDK Streamable HTTP MCP server, client, and Web Scout federation
Implemented and live migration verified: PostgreSQL checkpoint, audit-event, and worker-lease schema foundation
Implemented and live verified: atomic worker claim/reclaim/renew/release plus checkpoint and audit repositories
Implemented and live verified: background execution claims, renews, releases, audits, and checkpoints through PostgreSQL worker ownership
Implemented and live verified: startup discovery of abandoned queued/running work and per-node LangGraph PostgreSQL checkpoint resume
Implemented and contract tested: standalone research sources, provider capabilities, and dependency readiness endpoints
Implemented and contract tested: tenant-scoped durable cancellation across PostgreSQL, worker tasks, SSE, REST, and Vue
Implemented and tested: domain-neutral Intent Router, Planner, and Direct Answer agents; routing and plan-outline prompts no longer name or favor engineering vocabulary
Implemented and tested: demo_profiles/engineering/ isolates demo queries, evaluation cases, a reference report outline, and a private-knowledge manifest from core application code, with no company or organization branding
Implemented and tested: high-risk domain detection (medical, legal, financial, safety/security) on the Intent Router, propagated through the workflow to a human_review_required flag on the final reflection decision regardless of citation quality
Implemented and tested: the MCP server now exposes all seven charter research tools (search_web, search_private_documents, retrieve_source, ingest_document, save_research_report, get_research_history, request_human_review) alongside the original reference-card demo tool, each degrading independently when its own credentials are missing
Implemented and tested: a research_agent_steps table and repository for a durable per-agent-role trace, migrated and live-verified (wiring into live execution followed as a separate entry below)
Implemented and tested: a report-export service storing durable report snapshots through the existing DocumentStorage interface (local filesystem or S3), plus a REST endpoint to trigger and retrieve one
Implemented and tested: per-request correlation IDs attached to every log line and echoed as a response header
Implemented and tested: a closed/open/half-open circuit breaker, wired into the Tavily search executor, then extended to the Anthropic client and the Milvus vector store
Implemented and verified: a PostgreSQL/Redis GitHub Actions integration job running live integration tests against real service containers
Implemented: docs/PROJECT_CHARTER.md plus docs/{architecture,workflow,data-model,deployment,reliability,security,evaluation,trade-offs}.md, all free of company-specific naming
Implemented and tested: Vue Router, Pinia, and TanStack Query for the frontend, plus a Playwright end-to-end suite
Implemented and tested: an optional CORS allowlist, disabled by default, and Redis idempotency-lock lease renewal for executions that outlive the coordination lock's TTL
Implemented and tested: GET /research-runs (list) and GET /research-runs/{research_run_id} (single), both tenant-scoped
Implemented and live verified: real authentication replacing the pre-authentication X-Tenant-ID/X-User-ID headers — Argon2id password hashing, a durable sessions table (the charter's data-model item, previously deliberately deferred), httpOnly session cookies, self-service tenant signup, and matching Login/Register views with router guards on the frontend
Implemented and live verified: research_agent_steps wired into live execution via LangGraph's astream(stream_mode=["tasks", "values"]), tracing every canonical agent step as a real run executes, confirmed against the real production graph and a real Ollama call
Implemented and tested: exponential backoff with full jitter (app/core/retry.py), wired around the actual connectivity-level failures of Ollama, Tavily, and Milvus search -- deliberately not Anthropic, whose SDK already retries internally, and deliberately layered outside the circuit breaker rather than inside it
Implemented and tested: scripts/run_evaluation.py, a reproducible evaluation harness over evaluation_cases.jsonl (routing accuracy, source coverage, private-knowledge accuracy, report-section coverage, completion rate, human-review trigger rate, latency); scoring/loading unit tested and the harness itself smoke-tested end-to-end locally, but no run against a real provider has been published
Implemented and tested: an AcademicAwareSearchClient fanning out to Tavily and the Semantic Scholar Academic Graph API concurrently, with per-leg fail-open and a dedicated circuit breaker around the academic leg; source_type/authors/year/venue flow through evidence scoring (a +0.10 paper bonus) and citations end to end; live-network verified that a real Semantic Scholar failure does not break Tavily results, but a live PAPER- source inside a generated report is not yet published, blocked by that provider's unauthenticated rate limit on the verifying network
Implemented and tested: report export now accepts format (markdown/pdf) and citation_style (numbered/footnote) query params, rewriting citation markers into a real-link References/Notes list and rendering PDF via Markdown -> HTML -> WeasyPrint with a branded stylesheet; DownloadOptionsMenu in the Vue console offers all four combinations; verified inside the production Docker image and GitHub Actions CI, since WeasyPrint's native libraries are not installable on this dev machine's host OS
Implemented and tested: six published evaluation runs found and fixed a real crash bug (AnalystAgent.analyze() had no fallback for a truncated structured response) and a scoring-method defect (report-section coverage was an all-or-nothing pass/fail veto despite its own documented loose-matching intent); fixing the latter alone moved a qwen3:8b run from 20% to 80% overall pass rate with every underlying rate unchanged, confirming the gate -- not model capability -- was the dominant blocker; the one remaining failure is the same unresolved private-knowledge citation gap established across four earlier runs
Deployed and AWS-verified: the full staging application stack (ECS Fargate, RDS PostgreSQL, ElastiCache Valkey, ALB, CloudFront) applied for the first time and confirmed healthy at a real public URL, with a complete deep-research run against Claude recorded end to end (see the root README's Demo section). Getting there took nine real deploy attempts, each surfacing a genuinely different bug rather than a repeat of the same one: four rounds of missing IAM permissions on the GitHub OIDC deploy role (budgets, S3 bucket sub-resource reads, KMS grants for RDS's managed master-password secret, an ELB listener-attributes read), a combined-inline-policy-size limit forcing a move to a customer-managed IAM policy, two application bugs only reachable through the cloud path -- a `Literal[256, 512, 1024]` Pydantic field that does not coerce a string env var the way a plain `int` field does, and an asyncpg `?ssl=require` query parameter that raw psycopg/libpq rejects outright and expects as `sslmode` instead -- a QEMU arm64 cross-build crash under GitHub Actions' x86_64 runners, and an ECR immutable-tag collision on retry (fixed by making the deploy script skip already-pushed image tags). The first demo recording attempt also caught a live production crash -- `ResearchTask.rationale`'s 300-character limit was too tight for Claude's actual explanatory text and took down the whole workflow uncaught -- fixed by raising every sibling free-text field in the plan schema to 500 characters; the second recording completed in 4m35s with a verified report (100% citation coverage, 19/42 sources cited). Every partially-created deployment along the way, including one with a live ALB, RDS instance, and CloudFront distribution, was destroyed immediately after diagnosis to stop billing before the next fix landed. Bedrock's live embedding invocation remains unobserved, since the recorded run used only public sources and never triggered private-document upload.
```

See [workflow.md](workflow.md) for the deep-research agent path and
`ResearchState` shape, and [architecture.md](architecture.md) for the
request-flow, caching, idempotency, and rate-limiting sequences this log
used to spell out inline.

## Architecture, Annotated With Deployment Status

The diagram below combines the implemented application with its AWS staging
runtime — the ECS, RDS, Valkey, ALB, CloudFront, and ECR resources have been
applied and AWS-verified (demo-on-demand: applied for review sessions, not
always-on, so a specific check may catch the stack destroyed between
reviews). See [architecture.md](architecture.md) for a clean component
diagram without status annotations.

```mermaid
flowchart TB
    researcher["Researcher in browser"]
    cloudfront["CloudFront HTTPS entry<br/>applied and AWS-verified"]
    alb["Application Load Balancer<br/>applied and AWS-verified"]

    subgraph ecs["ECS Fargate task - applied and AWS-verified"]
        frontend["Nginx + Vue 3 console"]
        api["FastAPI API"]
        jobs["Background Job Manager"]
        workflow["LangGraph orchestrator"]
    end

    subgraph agents["Canonical eight-agent research workflow - implemented and tested"]
        router["1. Intent Router"]
        planner["2. Planner"]
        web["3. Web Scout"]
        local["4. Local Scout"]
        judge["5. Evidence Judge"]
        analyst["6. Analyst"]
        reflect["7. Reflect"]
        writer["8. Writer"]
        direct["Direct answer branch"]
    end

    subgraph state["Application state"]
        postgres["RDS PostgreSQL<br/>durable runs, reports, and evidence<br/>applied and AWS-verified"]
        redis["ElastiCache for Valkey<br/>cache, idempotency, locks, rate limits, and progress<br/>applied and AWS-verified"]
        milvus["Zilliz Cloud / Milvus<br/>tenant-scoped vector retrieval<br/>connection live verified"]
    end

    subgraph providers["External provider boundaries"]
        claude["Claude<br/>structured LLM output live verified"]
        tavily["Tavily<br/>web search live verified"]
        semanticscholar["Semantic Scholar<br/>academic search, unauthenticated by default<br/>fail-open leg, live rate-limit hit verified"]
        embeddings["Embedding provider<br/>Ollama live verified locally<br/>Bedrock adapter unit tested, live invocation not yet observed"]
        objects["Source object storage<br/>local filesystem tested<br/>private S3 applied and AWS-verified"]
        mcp["Internal MCP reference server<br/>official SDK + live TCP verified"]
    end

    researcher --> cloudfront --> alb --> frontend --> api
    api --> jobs --> workflow --> router
    router -->|simple request| direct --> claude
    router -->|deep research| planner
    planner --> web
    planner --> local
    web --> tavily
    web --> semanticscholar
    local --> embeddings --> milvus
    api --> objects
    web --> judge
    local --> judge
    mcp -. optional evidence .-> judge
    judge --> analyst --> reflect
    reflect -->|evidence gap and budget available| web
    reflect -->|private evidence gap| local
    reflect -->|quality gate passed| writer
    workflow <--> claude
    api <--> redis
    api <--> postgres
    writer --> postgres
    redis -->|SSE progress| api
    api -->|report, quality, and evidence| frontend
```

Terraform is the Infrastructure as Code tool for the planned AWS boundary in
this diagram. The application code says how the platform behaves; Terraform
says which AWS resources should exist and how they connect. `terraform plan`
previews the difference between the declaration and recorded state,
`terraform apply` creates or changes resources, the remote state records what
Terraform manages, and the guarded destroy workflow removes the billable
staging resources after a demo. A successful plan is validation, not a
deployment.

## Latest Verified Test-Run Snapshots

Backend (`ruff check .`, `mypy app tests scripts alembic/env.py
alembic/versions`, `pytest -q`):

```text
656 passed
28 integration tests deselected
1 dependency deprecation warning
```

The warning comes from the current FastAPI/Starlette test-client dependency
combination and does not represent a failed application test. The default
test suite does not call Claude, Tavily, Ollama, Milvus, PostgreSQL, or
Redis.

Frontend (`npm run lint`, `npm run format:check`, `npm run typecheck`, `npm
test`, `npm run build`, `npx playwright test`):

```text
Vue and TypeScript typecheck passed
50 component, store, and API-contract tests passed
Vite production build passed
13 Playwright end-to-end tests passed (auth, navigation, design-preview,
  direct-run-hydration)
```

The console uses the real asynchronous API contract: it authenticates
through the session cookie, submits durable jobs, consumes SSE with `fetch`,
retrieves completed reports, and presents evidence scores and source links.
Recent-run history remains browser-local until a tenant-scoped history
endpoint is implemented. The evidence panel is collapsed by default so the
report keeps a readable line length; a citation or evidence action expands
the traceable source details only when needed. Visual implementation
evidence and the source-to-build comparison are recorded in `design-qa.md`.
