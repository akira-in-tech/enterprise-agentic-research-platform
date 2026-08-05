# Reliability

## Implemented

- **Per-task timeout and failure isolation** — `SearchExecutor` bounds
  concurrency and isolates one task's failure from the rest of a plan.
- **Circuit breaker** (`app/core/circuit_breaker.py`) — closed/open/
  half-open state machine wired into `SearchExecutor` around Tavily. Once
  a run sees enough consecutive failures, later tasks in that run fail
  fast locally instead of each waiting out its own timeout. Not yet wired
  into Anthropic or Milvus call sites (see the commit that added it for
  why: each has multiple call sites, unlike Tavily's single `search()`).
- **Durable worker ownership** — PostgreSQL lease claim, heartbeat renewal,
  token-checked release, and startup discovery of abandoned queued/running
  work (`app/services/research/jobs.py`).
- **Checkpoint and resume** — official LangGraph `AsyncPostgresSaver` plus
  application-level `research_checkpoints` at node boundaries.
- **Idempotent request coordination** — `Idempotency-Key` requests fail
  closed (503) when Redis cannot guarantee exactly-once execution;
  concurrent duplicate requests get 409; a completed retry replays the
  original response.
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

- **CORS** — no `CORSMiddleware` is configured yet.
- **Exponential backoff with jitter** on provider calls — timeouts and
  circuit-breaking exist; explicit backoff-with-jitter retry does not.
- **Circuit breakers for Anthropic and Milvus** — see above.
- **Lock renewal for idempotency leases longer than the coordination TTL**
  — the 300-second default is a known bound, documented in the root
  README, not yet addressed.

## Budgets

Deep research is bounded by `max_iterations` (Reflect's supplementary-round
budget) and `max_writer_attempts` (Writer's citation-repair budget), both
enforced in `app/workflow/graph.py`. There is no unbounded loop anywhere in
the workflow.
