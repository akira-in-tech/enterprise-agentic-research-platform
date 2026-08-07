export type UserFacingProvider = "qwen" | "claude";

export type ProgressStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface CancelResearchRunResponse {
  research_run_id: string;
  status: "cancelled";
}

export type ResearchAgentId =
  | "intent_router"
  | "planner"
  | "web_scout"
  | "local_scout"
  | "evidence_judge"
  | "analyst"
  | "reflect"
  | "writer";

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

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
}

export interface AuthTenant {
  id: string;
  name: string;
  slug: string;
}

export interface AuthIdentity {
  user: AuthUser;
  tenant: AuthTenant;
}

export type KnowledgeDocumentStatus = "pending" | "indexing" | "ready" | "failed" | "deleting";

export interface KnowledgeDocument {
  id: string;
  tenant_id: string;
  uploaded_by_user_id: string | null;
  filename: string;
  media_type: "text/plain" | "text/markdown" | "application/pdf";
  byte_size: number;
  content_sha256: string;
  status: KnowledgeDocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  indexed_at: string | null;
}

export type ResearchRoute = "direct" | "deep_research";

export interface ResearchRun {
  research_run_id: string;
  llm_provider: "anthropic" | "ollama";
  status: ProgressStatus;
  query: string;
  route: ResearchRoute | null;
  route_reason: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
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

export type ReportSourceType = "web" | "paper";

export type ReportExportFormat = "markdown" | "pdf";

export type ReportCitationStyle = "numbered" | "footnote";

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
  source_type: ReportSourceType;
  authors: string[];
  year: number | null;
  venue: string | null;
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
