import type { RecentResearchRun, ResearchReport } from "../types/research";

export function createDesignPreviewRuns(now = new Date()): RecentResearchRun[] {
  const minutesAgo = (minutes: number): string =>
    new Date(now.getTime() - minutes * 60_000).toISOString();

  return [
    {
      id: "d38f3124-7d77-4bda-b711-10ca1e39f460",
      query: "How should a multi-tenant API isolate data across PostgreSQL and Redis?",
      provider: "qwen",
      status: "running",
      message: "Gathering evidence · 6 sources",
      sourceCount: 34,
      updatedAt: minutesAgo(2),
    },
    {
      id: "7d955d06-04a0-4d87-a2af-3a9b69f00ae5",
      query: "Compare transactional outbox and change data capture for event delivery",
      provider: "claude",
      status: "completed",
      message: "Report ready",
      citationCoverage: 0.94,
      sourceCount: 67,
      updatedAt: minutesAgo(48),
    },
    {
      id: "10ce205c-24b2-47d4-8b68-26482162fae8",
      query: "Evaluate failure modes in a Redis-backed idempotency design",
      provider: "qwen",
      status: "failed",
      message: "Provider unavailable · Retry",
      sourceCount: 19,
      updatedAt: minutesAgo(190),
    },
  ];
}

export function createDesignPreviewReport(now = new Date()): ResearchReport {
  return {
    report_id: "preview-report-1",
    research_run_id: "7d955d06-04a0-4d87-a2af-3a9b69f00ae5",
    content:
      "Use a transactional outbox when the database write and event publication must share one atomic boundary. Add change data capture when downstream fan-out, operational decoupling, and near-real-time replication matter more than keeping the publishing path simple.\n\nFor a high-volume platform, the strongest default is an outbox table captured by CDC: the application commits business data and the outbox record together, while the CDC layer publishes independently with observable lag, replay, and idempotent consumers.",
    workflow_status: "report_completed",
    citation_valid: true,
    citation_coverage: 0.94,
    reflection_status: "approved",
    reflection_reasons: [],
    reflection_attempts: 1,
    created_at: now.toISOString(),
    sources: [
      {
        source_id: "web-transactional-outbox",
        origin: "web",
        title: "Transactional outbox pattern",
        locator: "https://microservices.io/patterns/data/transactional-outbox.html",
        provider: "web",
        relevance: 0.98,
        content_quality: 0.94,
        traceability: 1,
        overall_score: 0.97,
        cited: true,
        source_type: "web",
        authors: [],
        year: null,
        venue: null,
      },
      {
        source_id: "web-cdc-overview",
        origin: "web",
        title: "Change data capture design considerations",
        locator: "https://debezium.io/documentation/reference/stable/architecture.html",
        provider: "web",
        relevance: 0.95,
        content_quality: 0.96,
        traceability: 1,
        overall_score: 0.96,
        cited: true,
        source_type: "web",
        authors: [],
        year: null,
        venue: null,
      },
      {
        source_id: "private-reliability-notes",
        origin: "private",
        title: "Internal delivery reliability requirements",
        locator: "https://example.com/private/reliability-requirements",
        provider: "private-rag",
        relevance: 0.93,
        content_quality: 0.91,
        traceability: 0.96,
        overall_score: 0.93,
        cited: true,
        source_type: "web",
        authors: [],
        year: null,
        venue: null,
      },
    ],
  };
}
