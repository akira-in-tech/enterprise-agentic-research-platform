# Enterprise Agentic Research Platform

An enterprise engineering research platform for backend, infrastructure, cloud,
networking, and distributed-systems questions.

The project is being built incrementally with FastAPI, LangGraph, Claude,
Qwen through Ollama, Tavily, PostgreSQL, Redis, Milvus, and MCP. A component is
listed as tested only after its automated checks pass in this repository.

## Project Status

| Component | Status |
| --- | --- |
| FastAPI application and health endpoint | Tested |
| Provider-neutral LLM interface | Tested |
| Claude provider | Tested with mocks |
| Qwen provider through Ollama | Tested with HTTP mocks |
| Intent router | Tested |
| Structured research planner | Tested |
| LangGraph routing and planning workflow | Tested |
| Tavily search provider | Tested with mocks |
| Bounded concurrent search executor | Tested |
| Per-task search timeout and failure isolation | Tested |
| Milvus private knowledge retrieval | Planned |
| PostgreSQL persistence | Planned |
| Redis caching and coordination | Planned |
| MCP tools and client | Planned |
| Evidence scoring and citation validation | Planned |
| React frontend | Planned |
| Docker Compose | Planned |
| GitHub Actions | Planned |
| AWS deployment | Planned |
| Open-source contribution | Planned |

There are no measured evaluation results and no deployed environment yet.

## Local Verification

Create the virtual environment and install the application with its development
dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the quality checks:

```bash
ruff check .
mypy app tests
pytest -q
```

Current verified result: 30 tests pass. The suite uses mocks and fake providers,
so it does not spend Claude or Tavily API credits.
