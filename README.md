# Enterprise Agentic Research Platform

A general-purpose enterprise research platform for evidence-backed questions
across technical, business, policy, market, and internal-knowledge domains.

The product is domain-neutral. Backend, infrastructure, cloud, networking,
database, and distributed-systems questions are used as the primary demo and
evaluation dataset because they align with the target engineering roles and
the HENNGE Global Internship Program.

The platform is being built incrementally with FastAPI, LangGraph, Claude,
Qwen through Ollama, Tavily, PostgreSQL, Redis, Milvus, and MCP. A component is
listed as tested only after its automated checks pass in this repository.

## Current Phase

```text
Completed: Phase 0 through Phase 10
Phase 10: MCP client boundaries and evidence-quality research pipeline
Next: Phase 11 - durable reports and asynchronous delivery
```

Phase 8 completed durable research execution and user-selectable LLM providers:

```text
FastAPI request
→ tenant and user scope
→ Claude or Qwen selection
→ canonical Anthropic or Ollama provider
→ queued PostgreSQL research run
→ running transition
→ LangGraph workflow
→ completed or failed transition
→ API response
```

The real Qwen path has been integration tested through:

```text
FastAPI
→ Qwen through Ollama
→ structured intent routing
→ direct answer generation
→ PostgreSQL lifecycle persistence
→ tenant-scoped database verification
→ cleanup
```

The Redis-backed API path has also been live integration tested:

```text
first FastAPI request
→ PostgreSQL lifecycle persistence
→ Qwen through Ollama
→ Redis result write with TTL
→ cache_hit=false

second tenant/provider/query-equivalent request
→ new durable PostgreSQL research run
→ Redis result read
→ Qwen workflow skipped
→ cache_hit=true
→ PostgreSQL and Redis test cleanup
```

The idempotent API and Redis coordination paths have been verified across live
API tests, live Redis tests, and deterministic concurrency coverage:

```text
first request with Idempotency-Key
→ validate a canonical request fingerprint
→ acquire a short-lived Redis lock with SET NX EX
→ double-check for a completed record
→ execute and persist one research run
→ store the completed idempotency response
→ release the lock only when the owner token still matches

concurrent request with the same key
→ lock acquisition rejected
→ workflow not executed a second time
→ API maps the in-progress result to HTTP 409

later retry with the same key and payload
→ replay the original research run and response
→ idempotency_replayed=true
```

Research progress coordination has been verified against a live Redis service:

```text
queued PostgreSQL research run
→ tenant-scoped Redis progress snapshot
→ running snapshot visible while the workflow is blocked
→ completed or failed terminal snapshot
→ GET /research-runs/{run_id}/progress
→ cross-tenant lookup returns no record
→ bounded TTL and test cleanup
```

Phase 10 completes the evidence-quality path for deep research:

```text
MCP Streamable HTTP tool boundary
→ canonical Web, Private, or MCP evidence
→ deterministic relevance, content-quality, and traceability scores
→ analyst report with canonical source IDs
→ unknown-citation and uncited-claim audit
→ reflection quality gate
→ report and quality state in the workflow, cache, and API
```

## Project Status

| Component | Status |
| --- | --- |
| FastAPI application and health endpoint | Tested |
| Provider-neutral LLM interface | Tested |
| Claude provider | Tested with mocks |
| Qwen LLM provider through Ollama | Tested with mocks and live integration test |
| Intent router with deterministic fallback | Tested |
| Direct-answer agent | Tested |
| Structured research planner | Tested |
| LangGraph routing and planning workflow | Tested |
| Tavily search provider | Tested with mocks and live smoke test |
| Bounded concurrent search executor | Tested |
| Per-task search timeout and failure isolation | Tested |
| URL normalization and stable web source IDs | Tested |
| TXT and Markdown private-document parsing | Tested |
| PDF text extraction | Tested |
| Deterministic document chunking | Tested |
| Provider-neutral embedding interface | Tested |
| Qwen embeddings through Ollama | Tested with mocks and live smoke test |
| Provider-neutral vector-store interface | Tested |
| In-memory vector store | Tested |
| Milvus collection initialization | Tested |
| Milvus vector upsert, search, and deletion | Tested with unit and live integration tests |
| Tenant-scoped private knowledge retrieval | Tested |
| Canonical private source generation | Tested |
| Ollama-to-Milvus private RAG pipeline | Live integration tested |
| Vector-store provider factory | Tested |
| Per-request Claude/Qwen user selection | Tested |
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
| MCP Streamable HTTP tools client | Contract tested with deterministic HTTP transport |
| Web, private, and MCP evidence normalization | Tested |
| Explainable evidence scoring and citation validation | Tested |
| Analyst report generation and reflection quality gate | Tested |
| Deep-research evidence-quality LangGraph path | Tested |
| Citation and reflection API/cache visibility | Tested |
| Durable report persistence | Planned |
| Iterative reflection loop | Planned |
| SSE progress streaming | Planned |
| Vue 3 + TypeScript + Vite frontend | Planned |
| Docker Compose project stack | Planned |
| GitHub Actions | Planned |
| AWS deployment | Planned |
| Open-source contribution | Planned |

There are no published evaluation metrics or deployed environments yet.
Local Docker services and mocked providers are not described as production
deployments.

## Current Architecture

### Public Web Retrieval

```text
Engineering question
→ structured planner
→ bounded concurrent search tasks
→ Tavily
→ URL normalization
→ deduplication
→ stable WEB-* sources
```

### Private Knowledge Retrieval

```text
Private document
→ validation and text extraction
→ deterministic chunks
→ embedding provider
→ vector-store provider
→ tenant-scoped similarity search
→ stable PRIVATE-* sources
```

### Provider Boundaries

```text
LLMClient
├── Claude
└── Qwen through Ollama

EmbeddingClient
├── Deterministic test embeddings
└── Qwen embeddings through Ollama

VectorStore
├── InMemoryVectorStore
└── MilvusVectorStore
```

Unit tests use mocks, deterministic providers, and the in-memory vector store.
Real external integrations are opt-in.

### MCP Tool Boundary

```text
StreamableHTTPMCPClient
→ initialize and negotiate protocol version 2025-11-25
→ send notifications/initialized
→ preserve MCP session and protocol headers
→ follow tools/list cursor pagination
→ call tools/call and validate content or structuredContent
→ distinguish JSON-RPC protocol errors from tool execution errors
→ terminate the session and close owned HTTP resources
```

The client implements the JSON-response subset of the
[MCP protocol revision 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
Streamable HTTP transport using the existing `httpx` dependency. Its lifecycle,
headers, pagination, tool-call results, error handling, and cleanup are contract
tested with a deterministic HTTP transport. No external MCP server is
configured or described as live.

### Evidence Quality Pipeline

```text
deep-research web sources
→ provider-neutral EvidenceSource records
→ explainable EvidenceScore records
→ evidence-constrained analyst prompt
→ Markdown report with canonical [SOURCE-ID] citations
→ CitationAudit
→ ReflectionDecision: approved or revise
```

The same evidence model also accepts tenant-scoped private sources and
successful MCP text results. The scorer is deterministic and records separate
relevance, content-quality, and traceability signals rather than presenting an
opaque model judgment. Reflection currently acts as one explicit quality gate;
automatic multi-pass revision remains planned.

### Durable Request Execution

```text
POST /research-runs
→ validate query and user-facing provider
→ normalize claude/qwen to anthropic/ollama
→ persist queued run
→ atomically mark running
→ execute LangGraph outside the database transaction
→ close provider-owned HTTP resources
→ atomically mark completed or failed
→ return run ID, provider, route, status, and answer
```

### Redis-Backed Result Caching

```text
POST /research-runs
→ create a durable PostgreSQL research run
→ look up tenant + canonical provider + normalized query in Redis
→ cache hit: restore API-visible state and skip the LLM workflow
→ cache miss: execute the workflow and commit the completed run
→ write the completed result to Redis with a bounded TTL
→ return cache_hit in the API response
```

Redis is an optional acceleration layer. Redis read or write failures are
logged and fail open, while PostgreSQL remains the durable source of truth.
Cache hits still create distinct research-run records for auditability.

### Idempotent Request Coordination

```text
POST /research-runs with Idempotency-Key
→ normalize the tenant-scoped client key and request payload
→ read a completed idempotency record
→ acquire an expiring Redis lock when no record exists
→ read the completed record again after acquiring the lock
→ execute at most once while the lease is held
→ store the completed response for later replay
→ release with an atomic compare-and-delete Lua script
```

Idempotency is a correctness feature rather than an optional acceleration.
Requests carrying `Idempotency-Key` fail closed with `503` when the Redis
record store or coordination lock is unavailable. Reusing a key for a
different payload, or retrying while its original request is still running,
returns `409`. A completed retry returns the original research-run ID without
creating another run.

The coordination lock currently has a bounded 300-second default TTL. That
prevents abandoned permanent locks, but lease renewal is still required before
executions longer than the TTL can be treated as production-safe.

### Tenant-Scoped Rate Limiting

```text
POST /research-runs
→ derive a versioned tenant-scoped Redis key
→ atomically increment the request counter with Lua
→ initialize a bounded TTL for the fixed window
→ allow requests within the configured tenant allowance
→ return HTTP 429 and Retry-After when the allowance is exhausted
→ expose X-RateLimit-Limit, Remaining, and Reset headers
```

The default policy allows 20 research requests per tenant per 60-second
window. Both values are configurable. Rate limiting fails closed with `503`
when Redis cannot guarantee enforcement, protecting the LLM-backed endpoint
from unbounded work during a coordination outage. The live Redis test verifies
concurrent atomic increments, tenant isolation, TTL behavior, and cleanup.

### Research Progress Coordination

```text
ResearchExecutionService
→ publish queued after durable run creation
→ publish running after the PostgreSQL transition
→ publish completed with the final workflow status
→ publish failed with a bounded error message
→ expire the latest snapshot with a configurable Redis TTL
```

Clients can poll `GET /research-runs/{research_run_id}/progress` with the
`X-Tenant-ID` header. Keys include both the tenant UUID and research-run UUID,
so another tenant cannot read the snapshot. Progress publishing fails open to
preserve durable research execution when Redis is unavailable; the query API
returns `503` when Redis cannot answer and `404` when no snapshot exists.

This is a lifecycle snapshot and polling foundation. The current research POST
endpoint still completes synchronously; background execution and SSE streaming
remain planned rather than being represented as implemented.

## Data Responsibilities

```text
PostgreSQL
→ durable business data
→ research runs
→ reports
→ sources
→ checkpoints

Redis
→ temporary cache
→ progress
→ rate limiting
→ idempotency and coordination

Milvus
→ private document chunks
→ embeddings
→ tenant-scoped vector similarity search
```

PostgreSQL persistence is implemented for tenants, users, research runs, and
research-run lifecycle transitions. Reports, source persistence, agent-step
records, and durable checkpoints remain planned.

Redis result caching is implemented with tenant/provider/query-scoped keys,
bounded TTLs, application-scoped connection management, fail-open behavior,
and live miss/write/hit verification. Tenant-scoped idempotency records,
canonical request fingerprints, atomic coordination locks, concurrent
execution exclusion, and completed-response replay are also implemented and
live tested. Tenant-scoped fixed-window rate limiting is implemented with
atomic Redis counters, bounded TTLs, API response headers, and live concurrent
verification. Tenant-scoped progress snapshots, lifecycle publishing, TTL,
polling API behavior, and live running-to-completed transitions are implemented
and tested. Lock renewal remains a production-hardening item for executions
that may exceed the coordination lease. Milvus private retrieval is implemented
and live integration tested.

## Local Setup

The project currently requires Python 3.13.

Create and activate the virtual environment:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

Install the application and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Copy the environment template:

```bash
cp .env.example .env
```

Add only the credentials required for the integrations you intend to run.

## Research API

The synchronous MVP endpoint requires:

- PostgreSQL with the current Alembic migration applied
- an existing tenant ID
- an optional user ID belonging to that tenant
- the selected provider configuration

The response includes `cache_hit` and `idempotency_replayed`. Redis result
caching accelerates repeated equivalent requests and fails open when
unavailable. Requests that explicitly include `Idempotency-Key` instead fail
closed when Redis cannot guarantee idempotency. Rate-limit enforcement also
fails closed, returns `429` when the configured tenant allowance is exhausted,
and exposes the current limit, remaining allowance, and reset delay in response
headers.

Start the API:

```bash
uvicorn app.main:app --reload
```

Submit a Qwen-backed request:

```bash
curl \
  -X POST \
  http://127.0.0.1:8000/research-runs \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: 00000000-0000-0000-0000-000000000000' \
  -H 'X-User-ID: 00000000-0000-0000-0000-000000000000' \
  -H 'Idempotency-Key: research-request-001' \
  -d '{
    "query": "What is a mutex?",
    "llm_provider": "qwen"
  }'
```

The tenant and user headers are an explicit pre-authentication MVP boundary.
They will be derived from authenticated identity rather than trusted directly
in a production deployment.

## Default Verification

Run the default quality checks:

```bash
ruff check .
mypy \
  app \
  tests \
  alembic/env.py \
  alembic/versions/0eea26dcdef5_create_research_persistence_tables.py
pytest -q
```

Current verified default result:

```text
386 passed
18 integration tests deselected
1 dependency deprecation warning
```

The warning comes from the current FastAPI/Starlette test-client dependency
combination and does not represent a failed application test.

The default test suite does not call Claude, Tavily, Ollama, Milvus,
PostgreSQL, or Redis.

## Live Integration Tests

Live tests require only the services used by the selected test:

- `RUN_LIVE_TESTS=true`
- a Tavily API key for the Tavily test
- Ollama with `qwen3:8b` for LLM tests
- Ollama with `qwen3-embedding:0.6b` for embedding tests
- Milvus listening at the configured `MILVUS_URI`
- PostgreSQL with the current Alembic migration applied for persistence tests
- Redis listening at the configured `REDIS_URL` for cache tests

Run individual integrations:

```bash
RUN_LIVE_TESTS=true \
pytest -q -m integration \
  tests/integration/test_tavily_live.py
```

```bash
RUN_LIVE_TESTS=true \
pytest -q -m integration \
  tests/integration/test_ollama_embeddings_live.py
```

```bash
RUN_LIVE_TESTS=true \
pytest -q -m integration \
  tests/integration/test_milvus_live.py
```

```bash
RUN_LIVE_TESTS=true \
pytest -q -m integration \
  tests/integration/test_private_rag_live.py
```

```bash
RUN_LIVE_TESTS=true \
OLLAMA_MODEL=qwen3:8b \
pytest -q -m integration \
  tests/integration/test_ollama_llm_live.py
```

```bash
DATABASE_URL=postgresql+asyncpg://research_user:change_me@localhost:5433/research_platform \
RUN_LIVE_TESTS=true \
pytest -q -m integration \
  tests/integration/test_research_execution_postgres_live.py
```

```bash
DATABASE_URL=postgresql+asyncpg://research_user:change_me@localhost:5433/research_platform \
REDIS_URL=redis://localhost:6379/0 \
RUN_LIVE_TESTS=true \
OLLAMA_MODEL=qwen3:8b \
pytest -q -m integration \
  tests/integration/test_research_api_live.py
```

Run the Redis-only integration checks without an LLM provider:

```bash
REDIS_URL=redis://localhost:6379/0 \
RUN_LIVE_TESTS=true \
pytest -q -m integration \
  tests/integration/test_redis_live.py \
  tests/integration/test_redis_idempotency_live.py \
  tests/integration/test_redis_rate_limit_live.py \
  tests/integration/test_redis_research_result_cache_live.py \
  tests/integration/test_research_execution_redis_live.py \
  tests/integration/test_research_idempotency_concurrency_live.py \
  tests/integration/test_research_progress_redis_live.py
```

The private-RAG test verifies the real path:

```text
private engineering documents
→ Qwen embeddings through Ollama
→ Milvus indexing
→ tenant-isolated semantic retrieval
→ canonical private sources
→ document deletion
→ temporary collection cleanup
```

## Engineering Principles

- Keep provider-specific SDK types behind application interfaces.
- Validate structured and external responses before using them.
- Validate complete vector batches before mutation.
- Enforce tenant isolation inside vector queries and deletion filters.
- Use deterministic mocks for default unit tests.
- Keep paid and external integration tests explicitly opt-in.
- Record only metrics that were produced by reproducible evaluation runs.
- Do not describe planned, mocked, or local-only features as production
  capabilities.

## Next Phase

Phase 10 is complete. Its tested scope is:

```text
MCP 2025-11-25 initialization and session lifecycle
cursor-paginated tools/list discovery
validated tools/call results and JSON-RPC errors
canonical Web, Private, and MCP evidence adapters
deterministic relevance, content-quality, and traceability scoring
canonical citation parsing and source allow-list validation
paragraph-level uncited-claim detection and coverage
evidence-constrained analyst report generation
reflection approval or revision decisions with explicit reasons
deep-research LangGraph integration
report-quality cache and API fields
```

Phase 11 will make reports durable and independently consumable:

```text
report and source persistence
research-run report retrieval APIs
background execution
SSE progress and completion delivery
iterative reflection and bounded revision policy
```

MCP is currently a contract-tested client boundary rather than a configured
external integration. PostgreSQL remains the durable source of truth, while
Redis stores temporary cache and coordination state. Coordination-lock renewal
for workflows that can exceed the current lease remains explicit production
hardening work.
