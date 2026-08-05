# Evaluation

There are no published evaluation metrics as of this writing. The platform
charter and this project's own engineering principles are explicit:
*"Record only metrics that were produced by reproducible evaluation runs"*
and *"Do not describe planned, mocked, or local-only features as
production capabilities."*

## What exists today

- `demo_profiles/engineering/queries.jsonl` — example requests with an
  `expected_route`, for manual or scripted routing-accuracy checks.
- `demo_profiles/engineering/evaluation_cases.jsonl` — richer structured
  cases (`min_independent_sources`, `requires_private_knowledge`,
  `expected_report_sections`) intended as fixtures for a future evaluation
  harness. **No harness consumes them yet** — they are reference content,
  not a running evaluation suite.

## What the charter calls for (not yet built)

- Routing accuracy
- Citation precision / unsupported-claim rate
- Source diversity
- Workflow completion rate and partial-failure recovery rate
- Latency and token usage per route
- Provider cost per research run
- Human-review trigger rate

Building this requires: a runner that executes each `evaluation_cases.jsonl`
entry against a real (or consistently mocked) deployment, scores the
result against its expectations, and writes a reproducible artifact
(timestamped, versioned against the commit that produced it). Until that
exists, any number quoted for these metrics is not backed by this
repository and should not be published.
