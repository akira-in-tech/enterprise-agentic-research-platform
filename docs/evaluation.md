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
  `expected_report_sections`).
- **`scripts/run_evaluation.py`** — a runner that authenticates against a
  running API instance, executes each case in an `evaluation_cases.jsonl`
  file through `POST /research-runs`, scores the outcome against its
  expectations, and writes a reproducible, timestamped, git-commit-tagged
  JSON report to `eval_runs/` (gitignored — a run artifact, not source).
  The scoring/loading logic (`app/services/evaluation/`) is unit tested
  against the real `demo_profiles/engineering/evaluation_cases.jsonl`
  fixture and against a mocked HTTP transport; the harness itself has been
  smoke-tested end-to-end against a live local instance (real Postgres,
  real Ollama/Qwen — no paid provider, no published metrics).

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

**No run against a real provider has been published.** Running the
harness for real is a deliberate, explicit action, not something this
repository or its CI does automatically — the same operating principle
already applied to `terraform apply` and live integration tests, since a
real run means real provider calls (and, with `--provider claude`, real
cost):

```bash
uvicorn app.main:app &
python scripts/run_evaluation.py \
  --cases-file demo_profiles/engineering/evaluation_cases.jsonl \
  --email you@example.com --password correct-horse-battery
```

## What the charter calls for beyond the above

- Citation precision / unsupported-claim rate as a dedicated metric
- Source diversity (not just count)
- Provider cost per research run (blocked on the API surfacing token
  usage at all)

Until a real run is published, any number quoted for these metrics is not
backed by this repository and should not be published.
