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
Completed: Phase 0 through Phase 8
Next: Phase 9 - Redis Caching and Coordination
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
| Redis caching and coordination | Planned |
| MCP tools and client | Planned |
| Evidence scoring and citation validation | Planned |
| Analyst and reflection loop | Planned |
| Report generation | Planned |
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

Redis is planned for Phase 9. Milvus private retrieval is implemented and live
integration tested.

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
228 passed
8 integration tests deselected
1 dependency deprecation warning
```

The warning comes from the current FastAPI/Starlette test-client dependency
combination and does not represent a failed application test.

The default test suite does not call Claude, Tavily, Ollama, Milvus, or
PostgreSQL.

## Live Integration Tests

Live tests require only the services used by the selected test:

- `RUN_LIVE_TESTS=true`
- a Tavily API key for the Tavily test
- Ollama with `qwen3:8b` for LLM tests
- Ollama with `qwen3-embedding:0.6b` for embedding tests
- Milvus listening at the configured `MILVUS_URI`
- PostgreSQL with the current Alembic migration applied for persistence tests

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
RUN_LIVE_TESTS=true \
OLLAMA_MODEL=qwen3:8b \
pytest -q -m integration \
  tests/integration/test_research_api_live.py
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

Phase 9 adds Redis caching and coordination:

```text
async Redis client foundation
health and connectivity checks
tenant-scoped cache keys
research-result caching
idempotency keys
short-lived coordination locks
rate-limit primitives
failure and reconnect behavior
unit and live integration tests
```

Redis will store temporary coordination state only. PostgreSQL remains the
durable source of truth for tenants, users, and research runs.
