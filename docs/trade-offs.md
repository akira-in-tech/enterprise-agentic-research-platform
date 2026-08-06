# Key Trade-offs

### Claude vs. Qwen

Claude gives higher quality and more reliable structured output; Qwen is
free to run locally, works offline, and keeps sensitive data on-premises.
Supporting both doubles the provider-behavior test matrix
(`app/services/llm/`), but keeps no business logic bound to a single
vendor.

### PostgreSQL, Redis, and Milvus

PostgreSQL is the durable source of truth (runs, reports, sources,
checkpoints, audit, agent steps). Redis is a fail-open/fail-closed
coordination and cache layer, never the durable record. Milvus is
similarity search only, never relational/billing data. Three storage
systems is more operational surface than one, but each has a job the
others do poorly (ACID transactions vs. sub-millisecond coordination vs.
vector similarity).

### LangGraph

Explicit workflow graph, conditional routing, and official Postgres
checkpointing buy crash-safe resume almost for free, at the cost of a
stricter state schema (`ResearchState`) than a plain function-call
pipeline would need.

### SSE vs. WebSocket

Research progress is server-to-client only, so SSE was chosen: simpler to
implement and proxy, reconnect-friendly. It would be the wrong choice for
high-frequency bidirectional collaboration, which this platform doesn't
need.

### Circuit breaker scope

A generic `CircuitBreaker` (`app/core/circuit_breaker.py`) was wired into
`SearchExecutor` around Tavily first, then extended to the Anthropic client
and the Milvus vector store as separate changes rather than all three at
once. Tavily has one `search()` entry point on the hot path of every
deep-research run; Anthropic and Milvus each have multiple call sites, so
retrofitting them without breaking existing test coverage was real,
separate work per integration. Shipping one well-tested integration at a
time beat shipping three rushed ones together.

### `research_agent_steps`: schema before wiring, then wired separately

The table, model, repository, migration, and both unit and live tests for
`agent_steps` shipped in one change; wiring it into
`app/services/research/execution.py` was a deliberately separate, later
change. That file already carried durable worker-lease, heartbeat, and
checkpoint-resume logic — folding a new per-node write path into it
deserved its own careful change rather than being rushed alongside the
schema addition. When it landed, the actual wiring used
`graph.astream(stream_mode=["tasks", "values"])` instead of the simpler
`graph.ainvoke()` specifically to get per-node start/finish events without
touching any of the eight agent node functions in `app/workflow/graph.py`
— confirmed by direct experimentation that manually replaying the
"values" stream reconstructs the exact same final state `ainvoke()`
returns, including across a durable resume.

### Retry wraps the circuit breaker, not the other way around

`call_with_backoff` (the outer layer) retries individual attempts that go
through `CircuitBreaker.call` (the inner layer), not the reverse. Retrying
outside the breaker means each attempt is independently subject to it, so
the breaker's failure count reflects real attempts against the
dependency; putting the breaker outside a retry loop would count a whole
retried operation as one failure, letting a truly-failing dependency stay
under the breaker's threshold far longer than intended. Every retryable
set is scoped to each client's actual transient-failure types and
deliberately excludes `CircuitBreakerOpenError` (a `RuntimeError`, not a
`MilvusException`/`httpx.TransportError`/etc.), so once the breaker is
open, a request fails on the first attempt instead of burning its retry
budget against a dependency it already knows is down.

### Authentication: server-side sessions, not JWT

The charter's data model names a `sessions` table, which points at
server-side sessions rather than stateless JWT — that's what got built:
an opaque, SHA-256-hashed token in an `httpOnly` cookie, resolved against
PostgreSQL on every request. The trade-off is an extra DB lookup per
request versus a stateless JWT; the payoff is that logout actually
revokes the session (a JWT needs a separate blocklist to support real
logout) and a leaked session row can't be turned back into a usable
token. Self-service registration always creates a brand-new tenant, which
made global `email` uniqueness the simpler choice over per-tenant
uniqueness — without an invite/switcher UI, the same email in two tenants
would make login ambiguous, and nothing today lets one email join a
second tenant anyway.

### Vue: framework choice, not a core dependency

`Vue 3 + TypeScript + Vite` was chosen for ecosystem fit and Composition
API modularity. The backend research engine has no dependency on the
frontend framework; swapping it would not touch `app/`.
