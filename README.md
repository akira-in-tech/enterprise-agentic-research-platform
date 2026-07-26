# Enterprise Agentic Research Platform

An enterprise engineering research platform for backend, infrastructure, cloud,
networking, database, and distributed-systems research.

The platform is being built incrementally with FastAPI, LangGraph, Claude,
Qwen through Ollama, Tavily, PostgreSQL, Redis, Milvus, and MCP. A component is
listed as tested only after its automated checks pass in this repository.

## Current Phase

```text
Completed: Phase 0 through Phase 7
Next: Phase 8 - PostgreSQL Persistence
```

Phase 7 completed the private-knowledge RAG foundation:

```text
TXT / Markdown / PDF
→ validated private document
→ deterministic chunking
→ Qwen embeddings through Ollama
→ provider-neutral vector store
→ Milvus indexing
→ tenant-scoped semantic retrieval
→ canonical private sources
```

## Project Status

| Component | Status |
| --- | --- |
| FastAPI application and health endpoint | Tested |
| Provider-neutral LLM interface | Tested |
| Claude provider | Tested with mocks |
| Qwen LLM provider through Ollama | Tested with HTTP mocks |
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
| Per-request Claude/Qwen user selection | Planned |
| PostgreSQL persistence | Planned |
| Redis caching and coordination | Planned |
| MCP tools and client | Planned |
| Evidence scoring and citation validation | Planned |
| Analyst and reflection loop | Planned |
| Report generation | Planned |
| Research REST API and SSE progress | Planned |
| React frontend | Planned |
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

PostgreSQL and Redis are planned for later phases. Milvus private retrieval is
implemented and integration tested.

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

## Default Verification

Run the default quality checks:

```bash
ruff check .
mypy app tests
pytest -q
```

Current verified default result:

```text
168 passed
4 integration tests deselected
1 dependency deprecation warning
```

The warning comes from the current FastAPI/Starlette test-client dependency
combination and does not represent a failed application test.

The default test suite does not call Claude, Tavily, Ollama, or Milvus.

## Live Integration Tests

Live tests require:

- `RUN_LIVE_TESTS=true`
- a Tavily API key for the Tavily test
- Ollama with `qwen3-embedding:0.6b`
- Milvus listening at the configured `MILVUS_URI`

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

Phase 8 adds PostgreSQL persistence with:

```text
SQLAlchemy
Alembic
users and tenants
sessions
research runs
agent steps
sources
reports
checkpoints
repository layer
transaction boundaries
```
