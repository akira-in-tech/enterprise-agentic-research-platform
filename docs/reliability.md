# Reliability

## Implemented

- **Exponential backoff with jitter** (`app/core/retry.py`) —
  `call_with_backoff` retries only a caller-declared tuple of transient
  exception types, using the "full jitter" algorithm
  (`sleep = uniform(0, min(max_delay, base * 2**attempt))`) to avoid a
  thundering herd against a recovering dependency. Wired around the
  connectivity-level failures each client actually raises: `OllamaClient`
  (`httpx.TransportError`), `SearchExecutor` around Tavily
  (`httpx.TransportError` plus Tavily's own `TimeoutError`), and
  `MilvusVectorStore.search()` (`MilvusUnavailableException`,
  `ConnectError`). Deliberately does not retry HTTP status errors (a 4xx
  is a bug, not a transient condition) or non-connectivity Milvus/Tavily
  errors (bad params, invalid API key) — retrying those would only delay
  the same failure. Anthropic is not wrapped: the SDK already retries
  internally (`max_retries=2`), and retrying an already-retried call would
  needlessly compound latency and cost.
- **Circuit breaker** (`app/core/circuit_breaker.py`) — closed/open/
  half-open state machine, wired around `SearchExecutor` (Tavily), the
  Anthropic client, and `MilvusVectorStore.search()`. Once a run sees
  enough consecutive failures, later calls in that run fail fast locally
  instead of each waiting out its own timeout. Retry is the outer layer
  and the breaker the inner one: each retry attempt is independently
  subject to the breaker, and `CircuitBreakerOpenError` is deliberately
  excluded from every retryable set, since retrying against an open
  breaker only wastes the backoff budget without ever reaching the
  dependency.
- **Per-task timeout and failure isolation** — `SearchExecutor` bounds
  concurrency and isolates one task's failure from the rest of a plan;
  the timeout budgets the whole operation, retries included.
- **CORS** — `CORSMiddleware` is added only when `CORS_ALLOWED_ORIGINS` is
  configured (empty by default), with `allow_credentials=True` for the
  session cookie and an explicit origin allowlist (never a wildcard).
- **Durable worker ownership** — PostgreSQL lease claim, heartbeat renewal,
  token-checked release, and startup discovery of abandoned queued/running
  work (`app/services/research/jobs.py`).
- **Checkpoint and resume** — official LangGraph `AsyncPostgresSaver` plus
  application-level `research_checkpoints` at node boundaries.
- **Durable per-agent-step trace** — `research_agent_steps` records a
  started/completed/failed row for each canonical agent node as real runs
  execute (`app/services/research/execution.py`), reconstructed from
  LangGraph's `astream(stream_mode=["tasks", "values"])` rather than a
  single opaque `ainvoke()`.
- **Idempotent request coordination** — `Idempotency-Key` requests fail
  closed (503) when Redis cannot guarantee exactly-once execution;
  concurrent duplicate requests get 409; a completed retry replays the
  original response. The coordination lock renews on a heartbeat
  (`redis_research_idempotency_lock_renew_interval_seconds`) for
  executions that outlive the lock's own TTL, mirroring the worker-lease
  heartbeat pattern.
- **Rate limiting** — tenant-scoped, fixed-window, fails closed.
- **Result caching and progress publishing** — Redis-backed, fail-open:
  their unavailability degrades performance/visibility, not correctness.
- **Cancellation as a first-class terminal state** — queued/running-only
  transition, distinct from a generic failure.
- **Correlation IDs** (`app/core/correlation.py`) — every request gets one,
  reused from `X-Correlation-ID` when safe, attached to every log line for
  that request, echoed in the response.
- **Human review for high-risk domains** — independent of citation/evidence
  quality, a request the Intent Router flags as medical, legal, financial,
  or safety-critical always carries `human_review_required=true` on its
  final `ReflectionDecision`, so a sufficiently-cited report is still never
  presented as an unqualified final decision.

## Not yet implemented

- **Retry-after-aware backoff for Tavily rate limits** —
  `UsageLimitExceededError`/`TavilyKeylessLimitError` carry a
  `retry_after_seconds` hint that `call_with_backoff` does not currently
  read; a rate-limited Tavily request falls through to the generic
  (non-retried) failure path today.

## Budgets

Deep research is bounded by `max_iterations` (Reflect's supplementary-round
budget) and `max_writer_attempts` (Writer's citation-repair budget), both
enforced in `app/workflow/graph.py`. There is no unbounded loop anywhere in
the workflow.
