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

### `research_agent_steps`: schema before wiring

The table, model, repository, migration, and both unit and live tests for
`agent_steps` shipped in one change; wiring it into
`app/services/research/execution.py` did not. That file already carries
durable worker-lease, heartbeat, and checkpoint-resume logic — folding a
new per-node write path into it deserved its own careful change rather
than being rushed alongside a schema addition. This mirrors an existing
pattern in the codebase (e.g. the Bedrock embedding adapter shipped
unit-tested with live invocation explicitly marked pending).

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
