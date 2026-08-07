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

## Second and third runs: after two rounds of real fixes

Two follow-up commits addressed the candidate follow-ups above,
directly targeting the root causes found in the first run:

1. `select_top_evidence()` caps what an Analyst/Writer prompt sees to
   the 20 highest-`overall`-scored sources, so low-relevance noise (like
   the "comparison" dictionary pages) competes far less with genuinely
   on-topic evidence — without removing anything from the source pool
   persisted or shown to users.
2. The Writer prompt was strengthened twice: first to require one
   Markdown `##` heading per outline item and to prefer the
   highest-`QUALITY_SCORE` source among competing citations; then, after
   the second live run below showed private-knowledge citation had
   *stopped* working, to add an explicit `ORIGIN` field to each
   evidence block and an instruction to prioritize `ORIGIN: private`
   evidence whenever the question uses "our"/"internal"/possessive
   language. The same origin-priority instruction was added to the
   Analyst prompt.

Two more live runs followed, same setup as the first (local Ollama
`qwen3:8b`, no paid provider, a fresh tenant each time so Redis's
result cache couldn't mask a re-execution):

| Metric | Run 1 (baseline) | Run 2 (capping + outline fix) | Run 3 (+ ORIGIN field + private-preference instruction) |
| --- | --- | --- | --- |
| Source coverage rate | 80% | 80% | **100%** |
| Private-knowledge accuracy | 100% | **0%** | 0% |
| Report-section coverage | 0% | 5% | 0% |
| Human-review trigger rate | 0% | 0% | 20% |
| Overall pass rate | 20% | 20% | 20% |

**Source coverage genuinely improved and held (80% → 100%)** — capping
the evidence pool to the top-scored sources measurably helped the
Writer cite enough independent sources.

**Report-section coverage and private-knowledge accuracy did not
reliably improve, despite two targeted, verified attempts.** The
private-knowledge regression in run 2 was root-caused, not guessed at:
inspecting the actual evidence pool for the onboarding-runbook case
showed the private document ranked **#1 and #2 by score** (0.73, 0.69 —
above every one of the 71 web sources in the same pool), yet the Writer
still cited web sources about generic onboarding best practices instead.
Run 3 gave the model everything it should have needed to get this
right — an explicit `ORIGIN: private` label on the evidence block and a
direct instruction to prefer it for possessive-language questions — and
the report was still about generic onboarding advice, never citing or
meaningfully reflecting the actual private document's content.

That is the honest conclusion to draw here: this is not evidence of a
retrieval bug, a scoring bug, or a missing instruction (all three were
checked and ruled out in turn), but a real capability ceiling of a
small local model on this kind of source-discipline-heavy task. Two
further rounds of legitimate prompt engineering moved one metric
(source coverage) and left two others flat or worse. Continuing to
iterate on `qwen3:8b`'s prompt alone is unlikely to be the highest-
leverage next step; the more informative next experiment is a
`--provider claude` run for comparison, which is deliberately not run
here since it is this project's first real-cost evaluation call and
needs its own explicit go-ahead (see charter principle on paid actions).

## Fourth run: enabling Qwen3 thinking mode

`app/services/llm/ollama.py` had `think` hardcoded to `false`, but
already contained dead-code handling for exactly the failure mode of
turning it on (an error raised when the token budget is spent on
reasoning with nothing left for the final answer) — a sign it had been
tried before and abandoned. Qwen3 is a hybrid-reasoning model, and the
two capability gaps runs 2-3 kept failing to move (outline adherence,
correct source prioritization) are exactly what chain-of-thought tends
to help with, so this was worth a real test: `think: true` was enabled
in both `generate_text` and `generate_structured`, `max_tokens` was
raised at every agent call site (`num_predict` bounds thinking +
response combined, not response alone — Writer went from 1,500 to
4,500, Analyst's structured call from 1,500 to 4,000, and so on down to
Intent Router's 200 → 600), and the client's HTTP timeout was raised
from 60s to 300s to give a single slower call room to finish.

| Metric | Run 1 (baseline) | Run 3 (prompt fixes, no thinking) | Run 4 (+ thinking mode) |
| --- | --- | --- | --- |
| Source coverage rate | 80% | 100% | 80% |
| Private-knowledge accuracy | 100% | 0% | 0% |
| Report-section coverage | 0% | 0% | 5% |
| Average latency | 204s | 266s | 283s |
| Overall pass rate | 20% | 20% | 20% |

The strict metrics did not move — but reading the actual report content
shows a real, substantial qualitative change that the metrics don't
capture. **The catastrophic topic drift from run 1 is gone.**
`eval-eng-004`'s report is now genuinely about Redis security (sections
titled "Redis Security Best Practices", "Hybrid Cloud Security
Challenges", "Secure Connection Methods for Redis" — no more Merriam-
Webster definitions of "comparison"), and `eval-eng-002`'s report now
mentions RabbitMQ, which it hadn't in any prior run. The reports are
also now multi-section by structure, just not using the exact heading
text `evaluation_cases.jsonl` expects, which is why report-section
coverage's case-insensitive *substring* match still scores near zero
against topically sound, differently-worded headings like "Key Features
of HTTP/3" instead of "Technical Background". That is a real, separate
finding about the scoring method's own blind spot, not only about the
model.

**Private-knowledge citation is still unfixed, and inspecting why
reveals a related but distinct problem.** The onboarding-runbook report
this run built its entire structure around a single generic web blog
post (down to lifting the blog's own "Help Improve This Post"
call-to-action as a report section), never citing the private document
that — as established in run 2's investigation — ranks #1 by score and
carries an explicit `ORIGIN: private` label. So the model isn't failing
to notice private evidence exists; it is fixating on one convenient web
source and mining it exhaustively instead of drawing from the
higher-priority evidence sitting alongside it. Thinking mode did not
change this behavior.

Net assessment: thinking mode is a real, worthwhile improvement to keep
(it fixed a worse failure mode — total topic drift — than the one
that's left), but it does not close the gap to a passing evaluation
score on this model, and it made every case slower (204s → 283s average
across runs 1 and 4). The evaluation harness's section-coverage metric
also deserves a follow-up look independent of any model change, since
it is now measurably under-crediting genuinely well-structured reports.
The `--provider claude` comparison recommended after run 3 remains the
next informative experiment and remains unrun pending explicit go-ahead.

## What the charter calls for beyond the above

- Citation precision / unsupported-claim rate as a dedicated metric
- Source diversity (not just count)
- Provider cost per research run (blocked on the API surfacing token
  usage at all)

The metrics above are backed by the published run. Anything not listed
in that table is still not backed by this repository and should not be
published.
