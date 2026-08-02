export type UserFacingProvider = "qwen" | "claude";

export type ProgressStatus = "queued" | "running" | "completed" | "failed";

export type ResearchAgentId =
  | "scope"
  | "plan"
  | "retrieve"
  | "private_rag"
  | "analyze"
  | "verify"
  | "synthesize"
  | "report";

export type OperationalIssueKind =
  | "redis_unavailable"
  | "sse_disconnected"
  | "job_failed"
  | "report_unavailable"
  | "citation_revision_required";

export interface OperationalIssue {
  kind: OperationalIssueKind;
  title: string;
  message: string;
  actionLabel?: string;
}

export interface WorkspaceContext {
  tenantId: string;
  userId: string;
}

export interface CreateResearchJobResponse {
  research_run_id: string;
  status: "queued";
  progress_url: string;
  events_url: string;
  report_url: string;
}

export interface ResearchProgressRecord {
  research_run_id: string;
  status: ProgressStatus;
  message: string;
  updated_at: string;
  workflow_status: string | null;
  error_message: string | null;
}

export interface ResearchReportSource {
  source_id: string;
  origin: "web" | "private" | "mcp";
  title: string;
  locator: string;
  provider: string;
  relevance: number;
  content_quality: number;
  traceability: number;
  overall_score: number;
  cited: boolean;
}

export interface ResearchReport {
  report_id: string;
  research_run_id: string;
  content: string;
  workflow_status: string;
  citation_valid: boolean;
  citation_coverage: number;
  reflection_status: "approved" | "revise";
  reflection_reasons: string[];
  reflection_attempts: number;
  created_at: string;
  sources: ResearchReportSource[];
}

export interface RecentResearchRun {
  id: string;
  query: string;
  provider: UserFacingProvider;
  status: ProgressStatus;
  message: string;
  updatedAt: string;
  eventsUrl?: string;
  reportUrl?: string;
  citationCoverage?: number;
  sourceCount?: number;
}
