# Research Workflow

## Routing

`IntentRouter.classify()` (`app/agents/intent_router.py`) asks the selected
LLM to choose `direct` or `deep_research` and to flag
`is_high_risk_domain`, using a domain-neutral prompt that lists the
platform's full domain range (engineering, market research, policy,
internal knowledge, and so on) rather than assuming engineering. A
deterministic, equally domain-neutral keyword rule
(`classify_route_by_rule`) is the fallback when the LLM call fails, plus a
separate `detect_high_risk_domain()` rule for the risk flag.

## Deep research path

```text
Planner
  → creates 2-6 sub-questions, 2-6 search tasks, and a 3-8 section outline
    whose sections fit the request's actual domain
  ├── Web Scout   → SearchExecutor → Tavily (circuit-breaker guarded)
  └── Local Scout → PrivateKnowledgeRetriever → Milvus (tenant-scoped)
  → Evidence Judge normalizes both pools, scores relevance/quality/
    traceability, and detects gaps and conflicts
  → Analyst produces structured findings with canonical source IDs
  → Reflect decides: write, or run one bounded supplementary round
    (and independently sets human_review_required for high-risk domains)
  → Writer produces a conclusion-first Markdown report with [SOURCE-ID]
    citations, then runs a bounded citation-repair loop against the
    citation validator's audit
```

## State

`ResearchState` (`app/workflow/state.py`) is the TypedDict threaded through
every LangGraph node. Notable fields:

- `route`, `route_reason`, `is_high_risk_domain` — set once by the router.
- `web_sources`, `private_sources`, `mcp_sources` — per-origin evidence
  pools before normalization.
- `evidence_sources`, `evidence_scores`, `evidence_gaps`,
  `evidence_conflicts` — Evidence Judge's output.
- `reflection_result` (loop control) vs `reflection` (final
  `ReflectionDecision`, including `human_review_required` /
  `human_review_reason`) — two distinct fields for two distinct decisions.
- `citation_audit` — the Writer loop's validator output.

## Durable execution

For `POST /research-runs/jobs`, `ResearchJobManager` claims a PostgreSQL
worker lease before running the graph, renews it on a heartbeat, and
records checkpoints/audit events at node boundaries via
`ResearchDurabilityRepository`. On startup, the application scans for
queued/running rows without an active lease and reclaims them, and the
official LangGraph `AsyncPostgresSaver` resumes a graph from its last
successful superstep rather than repeating it.

`research_agent_steps` (`app/db/models/agent_step.py`,
`app/db/repositories/agent_steps.py`) can additionally record one row per
agent-role transition for a finer trace than the checkpoint/audit tables
provide. As of this writing it is a tested, migrated table and repository
that is **not yet wired into the live execution path** — see the schema
addition's commit for the reasoning (the execution path's lease/heartbeat/
resume logic is sensitive enough to deserve its own dedicated change).
