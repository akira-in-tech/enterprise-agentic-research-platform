import type { RecentResearchRun } from "../types/research";

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
      updatedAt: minutesAgo(2),
    },
    {
      id: "7d955d06-04a0-4d87-a2af-3a9b69f00ae5",
      query: "Compare transactional outbox and change data capture for event delivery",
      provider: "claude",
      status: "completed",
      message: "Report ready",
      citationCoverage: 0.94,
      updatedAt: minutesAgo(48),
    },
    {
      id: "10ce205c-24b2-47d4-8b68-26482162fae8",
      query: "Evaluate failure modes in a Redis-backed idempotency design",
      provider: "qwen",
      status: "failed",
      message: "Provider unavailable · Retry",
      updatedAt: minutesAgo(190),
    },
  ];
}
