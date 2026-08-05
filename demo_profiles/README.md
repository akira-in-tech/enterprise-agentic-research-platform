# Demo Profiles

The core platform is domain-neutral: the Intent Router, Planner, and Direct
Answer agents (`app/agents/`) do not name or favor any single domain, company,
or vocabulary. This directory holds example content used to demonstrate and
evaluate the platform against one concrete domain at a time, kept separate
from that core code.

```text
demo_profiles/
└── engineering/
    ├── queries.jsonl          example requests and their expected route
    ├── evaluation_cases.jsonl structured cases for a future evaluation harness
    ├── report_profile.yaml    a reference report outline for this domain
    ├── kb_manifest.yaml       suggested private-knowledge documents for a
    │                          private-RAG demo (not shipped as real files)
    └── demo_walkthrough.md    the end-to-end demo path for this profile
```

`engineering/` is the first profile: backend, infrastructure, networking,
database, and distributed-systems questions, used because they produce
concrete, technically demanding research scenarios that are easy to verify.
It is not the only domain the platform can research, and it is not tied to
any specific company or organization.

Deleting this directory does not change the platform's ability to research
other domains (market research, product comparison, policy, or internal
knowledge) — the routing, planning, retrieval, evidence, and report-writing
code never imports from `demo_profiles/`. Additional profiles (for example
`market_research/` or `policy_research/`) can be added following the same
five-file structure without touching application code.

None of the files in this directory are currently loaded by the application
at runtime. They are reference and evaluation content for demos and for a
future evaluation harness, not an executable configuration format yet.
