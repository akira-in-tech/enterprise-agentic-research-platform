# Engineering Demo Walkthrough

This walkthrough exercises the platform's deep-research path end to end
using the `engineering` profile. It demonstrates general platform
capabilities; it is not a description of the platform's scope. See the root
[README](../../README.md) for what is currently tested versus planned.

## Path

```text
Start the local stack (docker compose up, or uvicorn + local Postgres/Redis)
→ open the Vue console
→ pick Claude or Qwen as the provider
→ submit a query from queries.jsonl, e.g.
  "Compare HTTP/2 and HTTP/3 using current technical sources."
→ Intent Router routes to deep_research (comparison + recency signals)
→ Planner produces sub-questions, search tasks, and a report outline
→ Web Scout and Local Scout run in parallel
→ Evidence Judge scores relevance, quality, and freshness; flags gaps/conflicts
→ Analyst produces structured findings with canonical source IDs
→ Reflect requests a bounded supplementary round if evidence is thin
→ Writer produces a conclusion-first Markdown report with [SOURCE-ID] citations
→ report and evidence sources persist to PostgreSQL
→ progress streams to the console over SSE
```

## Optional private-knowledge variant

To exercise `PRIVATE-*` sources instead of (or alongside) `WEB-*` sources:

1. Upload one or two documents from `kb_manifest.yaml` via `POST /documents`
   under your own tenant ID.
2. Submit `eng-008` from `queries.jsonl`
   ("Summarize our internal onboarding runbook for new backend engineers.").
3. Confirm the report cites `PRIVATE-*` source IDs and that a different
   tenant ID cannot retrieve the same document.

## What this profile is for

- Giving a reviewer a concrete, verifiable research scenario.
- Producing example queries and expected routes for manual or automated
  evaluation (`evaluation_cases.jsonl`).
- Illustrating one possible report shape (`report_profile.yaml`) for a
  technical domain.

## What this profile is not

- Not a claim that the platform only researches engineering topics — the
  routing, planning, retrieval, and report-writing code in `app/agents/`
  and `app/services/` is domain-neutral. Swap the queries and report
  profile for a different domain (market research, policy, academic
  literature) to demonstrate the same pipeline there instead.
