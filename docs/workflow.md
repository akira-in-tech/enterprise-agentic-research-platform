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
Intent Router
├── direct question → Direct Answer → END
└── deep research → Planner
                    ├── Web Scout ──┐
                    └── Local Scout ┘  run in parallel
                                      ↓
                               Evidence Judge
                                      ↓
                                   Analyst
                                      ↓
                                   Reflect
                    ├── evidence gap + budget → targeted scout round
                    └── sufficient evidence  → Writer → END
```

Planner creates 2-6 sub-questions, 2-6 search tasks, and a 3-8 section
outline whose sections fit the request's actual domain. Web Scout
(`SearchExecutor` → `AcademicAwareSearchClient` → Tavily + Semantic
Scholar concurrently, circuit-breaker and retry guarded) and Local
Scout (`PrivateKnowledgeRetriever` → Milvus, tenant-scoped) run in
parallel and are joined before Evidence Judge normalizes both pools,
scores relevance/quality/traceability, and detects gaps and conflicts.
Analyst produces structured findings with canonical source IDs. Reflect
decides whether to write or run one bounded supplementary round routed
back to either scout, and independently sets `human_review_required` for
high-risk domains regardless of citation quality. Writer produces a
conclusion-first Markdown report with `[SOURCE-ID]` citations, then runs a
bounded citation-repair loop against the citation validator's audit.

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
`app/db/repositories/agent_steps.py`) additionally records a
started/completed/failed row per agent-role transition — a finer trace
than the checkpoint/audit tables provide. `LangGraphResearchWorkflow`
(`app/services/research/execution.py`) reconstructs this from LangGraph's
`astream(stream_mode=["tasks", "values"])` rather than a single opaque
`ainvoke()`: "tasks" events drive the trace rows and the last "values"
event is the final state, confirmed to exactly match what `ainvoke()`
would return, including across a durable resume.
