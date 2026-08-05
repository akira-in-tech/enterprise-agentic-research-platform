import type {
  CancelResearchRunResponse,
  CreateResearchJobResponse,
  KnowledgeDocument,
  ResearchProgressRecord,
  ResearchReport,
  ResearchRun,
  UserFacingProvider,
  WorkspaceContext,
} from "../types/research";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export async function getApiHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

export class ResearchApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ResearchApiError";
  }
}

function tenantHeaders(workspace: WorkspaceContext): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Tenant-ID": workspace.tenantId,
  };

  if (workspace.userId) {
    headers["X-User-ID"] = workspace.userId;
  }

  return headers;
}

function requestHeaders(workspace: WorkspaceContext): HeadersInit {
  return {
    ...tenantHeaders(workspace),
    "Content-Type": "application/json",
  };
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export async function createResearchJob(
  query: string,
  provider: UserFacingProvider,
  workspace: WorkspaceContext,
): Promise<CreateResearchJobResponse> {
  const response = await fetch(`${API_BASE_URL}/research-runs/jobs`, {
    method: "POST",
    headers: requestHeaders(workspace),
    body: JSON.stringify({ query, llm_provider: provider }),
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as CreateResearchJobResponse;
}

export async function getResearchRun(
  researchRunId: string,
  workspace: WorkspaceContext,
): Promise<ResearchRun> {
  const response = await fetch(`${API_BASE_URL}/research-runs/${researchRunId}`, {
    headers: tenantHeaders(workspace),
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as ResearchRun;
}

export async function cancelResearchJob(
  researchRunId: string,
  workspace: WorkspaceContext,
): Promise<CancelResearchRunResponse> {
  const response = await fetch(`${API_BASE_URL}/research-runs/${researchRunId}/cancel`, {
    method: "POST",
    headers: requestHeaders(workspace),
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as CancelResearchRunResponse;
}

export function parseSseFrames(buffer: string): {
  frames: Array<{ event: string; data: string }>;
  remainder: string;
} {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const chunks = normalized.split("\n\n");
  const remainder = chunks.pop() ?? "";
  const frames = chunks.flatMap((chunk) => {
    let event = "message";
    const data: string[] = [];

    for (const line of chunk.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data.push(line.slice(5).trimStart());
      }
    }

    return data.length > 0 ? [{ event, data: data.join("\n") }] : [];
  });

  return { frames, remainder };
}

export async function streamResearchProgress(
  eventsUrl: string,
  workspace: WorkspaceContext,
  onProgress: (progress: ResearchProgressRecord) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${eventsUrl}`, {
    headers: requestHeaders(workspace),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const parsed = parseSseFrames(buffer);
    buffer = parsed.remainder;

    for (const frame of parsed.frames) {
      if (frame.event === "progress") {
        onProgress(JSON.parse(frame.data) as ResearchProgressRecord);
      } else if (frame.event === "error" || frame.event === "not_found") {
        const body = JSON.parse(frame.data) as { detail?: string };
        throw new ResearchApiError(body.detail ?? "Progress stream failed.", 503);
      }
    }

    if (done) {
      return;
    }
  }
}

export async function getResearchReport(
  reportUrl: string,
  workspace: WorkspaceContext,
): Promise<ResearchReport> {
  const response = await fetch(`${API_BASE_URL}${reportUrl}`, {
    headers: requestHeaders(workspace),
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as ResearchReport;
}

export async function listKnowledgeDocuments(
  workspace: WorkspaceContext,
): Promise<KnowledgeDocument[]> {
  const response = await fetch(`${API_BASE_URL}/documents`, {
    headers: tenantHeaders(workspace),
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as KnowledgeDocument[];
}

export async function uploadKnowledgeDocument(
  file: File,
  workspace: WorkspaceContext,
): Promise<KnowledgeDocument> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/documents`, {
    method: "POST",
    headers: tenantHeaders(workspace),
    body,
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as KnowledgeDocument;
}

export async function deleteKnowledgeDocument(
  documentId: string,
  workspace: WorkspaceContext,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
    method: "DELETE",
    headers: tenantHeaders(workspace),
  });

  if (!response.ok) {
    throw new ResearchApiError(await errorMessage(response), response.status);
  }
}
