# Evaluation

The platform charter and this project's own engineering principles are
explicit: *"Record only metrics that were produced by reproducible
evaluation runs"* and *"Do not describe planned, mocked, or local-only
features as production capabilities."* The numbers below are from a real
run; see [First published run](#first-published-run).

## What exists today

- `demo_profiles/engineering/queries.jsonl` — example requests with an
  `expected_route`, for manual or scripted routing-accuracy checks.
- `demo_profiles/engineering/evaluation_cases.jsonl` — richer structured
  cases (`min_independent_sources`, `requires_private_knowledge`,
  `expected_report_sections`).
- **`scripts/run_evaluation.py`** — a runner that authenticates against a
  running API instance, executes each case in an `evaluation_cases.jsonl`
  file through `POST /research-runs`, scores the outcome against its
  expectations, and writes a reproducible, timestamped, git-commit-tagged
  JSON report to `eval_runs/` (gitignored — a run artifact, not source).
  The scoring/loading logic (`app/services/evaluation/`) is unit tested
  against the real `demo_profiles/engineering/evaluation_cases.jsonl`
  fixture and against a mocked HTTP transport; the harness itself has been
  run for real end-to-end against a live local instance (real Postgres,
  real Ollama/Qwen, real Tavily/Semantic Scholar — no paid provider). See
  [First published run](#first-published-run) for the results.

What it scores, per case:

- **Routing accuracy** — actual route vs. `expected_route`.
- **Source coverage** — count of `cited: true` sources vs.
  `min_independent_sources`.
- **Private-knowledge accuracy** — whether a `requires_private_knowledge`
  case actually cited an `origin: "private"` source.
- **Report-section coverage** — case-insensitive substring match between
  `expected_report_sections` and the Markdown headings in the actual
  report (loose by design: an LLM will not reproduce section titles
  verbatim, so this checks structural intent, not exact wording).
- **Completion rate**, **human-review trigger rate**, and **latency**
  aggregated across the run.

What it does **not** yet measure: citation precision / unsupported-claim
rate (would need a separate claim-by-claim audit beyond the citation
validator's existing valid/invalid signal), source diversity (beyond a
raw count), and provider token usage or cost (the API does not currently
surface either).

Running the harness for real is a deliberate, explicit action, not
something this repository or its CI does automatically — the same
operating principle already applied to `terraform apply` and live
integration tests, since a real run means real provider calls (and, with
`--provider claude`, real cost):

```bash
uvicorn app.main:app &
python scripts/run_evaluation.py \
  --cases-file demo_profiles/engineering/evaluation_cases.jsonl \
  --email you@example.com --password correct-horse-battery
```

## First published run

Run at 2026-08-07, commit `882a5a7`, `--provider qwen` (local Ollama
`qwen3:8b`, no paid provider), against a local PostgreSQL/Redis instance
with `VECTOR_STORE_PROVIDER=memory` and a fabricated onboarding-runbook
document uploaded for the one `requires_private_knowledge` case. Report:
`eval_runs/eval-20260807T120254Z.json` (gitignored, not in this repo —
the numbers below are the full, unedited summary).

| Metric | Result |
| --- | --- |
| Cases | 5 |
| Routing accuracy | 100% |
| Completion rate | 100% (no crashes or timeouts once the per-request timeout was raised to 900s) |
| Source coverage rate | 80% (4/5 met `min_independent_sources`) |
| Private-knowledge accuracy | 100% |
| Report-section coverage | 0% |
| Human-review trigger rate | 0% |
| Average latency | 204s (real deep-research cases ran 300-360s each on local `qwen3:8b`; the one direct-route case ran in 13s) |
| **Overall pass rate** | **20% (1/5 — only the trivial direct-route case passed)** |

**The pipeline itself held up**: every case completed, routing was
perfect, and the private-RAG path correctly found and cited the seeded
document. The 20% pass rate is a genuine model-quality finding, not a
bug in the workflow, and the harness did exactly what it is for —
surfaced it instead of hiding it.

**Report-section coverage failed on every deep-research case** — the
Planner's 3-8 section outline was never followed. `qwen3:8b` wrote a
single flowing document with one H1 title (e.g. "HTTP/3 and QUIC: A
Concise Overview") instead of the requested `Executive Summary` /
`Technical Background` / `Trade-offs` / ... structure. This looks like a
prompt-adherence limitation of a small local model on multi-section
structured writing, not a retrieval or citation problem.

**Two cases drifted off the actual question, and it traces to source
selection, not retrieval.** Inspecting the underlying evidence pool for
`eval-eng-004` ("What is the current security posture recommendation for
exposing Redis to a public network?") shows Tavily *did* return strong,
on-topic sources — `redis.io/.../network-security`, "How to Protect
Redis from Common Attack Vectors", "Databases. EXPOSED! (Redis) -
Censys" — each scored 0.6-0.7 relevance. The Writer ignored all of them
and cited only the two *lowest*-relevance sources in the 70-source pool
(0.15 and 0.31): a Merriam-Webster definition of the word "comparison"
and its Wikipedia disambiguation page, apparently pulled in by a
sub-query Tavily matched loosely. The resulting report is titled
"Report: Understanding the Word 'Comparison' in B1 English" and never
mentions Redis. `eval-eng-002` ("Compare Kafka and RabbitMQ...") shows
the same pattern less severely: the report never mentions "RabbitMQ" at
all, instead comparing Kafka's KRaft to ZooKeeper. In both cases
retrieval worked; a small local model's source selection during writing
did not reliably prefer the higher-relevance evidence already sitting in
its own prompt.

This is not fixed as part of publishing this run — per the charter,
recording the real number takes priority over quietly tuning the run
until it looks better. Candidate follow-ups, none implemented yet:
filtering very-low-relevance sources out of the evidence pool before
they reach the Writer, strengthening the outline-adherence and
source-prioritization instructions in the Writer prompt, or evaluating
`--provider claude` for comparison (this would be the first real-cost
run and needs its own explicit go-ahead).

## What the charter calls for beyond the above

- Citation precision / unsupported-claim rate as a dedicated metric
- Source diversity (not just count)
- Provider cost per research run (blocked on the API surfacing token
  usage at all)

The metrics above are backed by the published run. Anything not listed
in that table is still not backed by this repository and should not be
published.
