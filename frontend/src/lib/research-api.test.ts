import { afterEach, describe, expect, it, vi } from "vitest";

import {
  cancelResearchJob,
  deleteKnowledgeDocument,
  getResearchRun,
  listKnowledgeDocuments,
  parseSseFrames,
  uploadKnowledgeDocument,
} from "./research-api";

afterEach(() => vi.unstubAllGlobals());

describe("parseSseFrames", () => {
  it("parses complete progress events and retains an incomplete frame", () => {
    const parsed = parseSseFrames(
      'event: progress\ndata: {"status":"running"}\n\nevent: progress\ndata: {"status"',
    );

    expect(parsed.frames).toEqual([
      {
        event: "progress",
        data: '{"status":"running"}',
      },
    ]);
    expect(parsed.remainder).toBe('event: progress\ndata: {"status"');
  });

  it("supports CRLF and multi-line data", () => {
    const parsed = parseSseFrames("event: error\r\ndata: first\r\ndata: second\r\n\r\n");

    expect(parsed.frames).toEqual([{ event: "error", data: "first\nsecond" }]);
    expect(parsed.remainder).toBe("");
  });
});

describe("research cancellation API", () => {
  it("cancels one run using the session cookie", async () => {
    const researchRunId = "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ research_run_id: researchRunId, status: "cancelled" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(cancelResearchJob(researchRunId)).resolves.toEqual({
      research_run_id: researchRunId,
      status: "cancelled",
    });
    expect(fetchMock).toHaveBeenCalledWith(`/api/research-runs/${researchRunId}/cancel`, {
      method: "POST",
      credentials: "include",
    });
  });
});

describe("research run lookup API", () => {
  it("fetches one run's lifecycle state using the session cookie", async () => {
    const researchRunId = "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589";
    const run = {
      research_run_id: researchRunId,
      llm_provider: "anthropic",
      status: "completed",
      query: "Compare HTTP/2 and HTTP/3.",
      route: "deep_research",
      route_reason: "Comparison requires current sources.",
      error_message: null,
      created_at: "2026-08-05T12:00:00Z",
      started_at: "2026-08-05T12:00:01Z",
      completed_at: "2026-08-05T12:01:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(run), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getResearchRun(researchRunId)).resolves.toEqual(run);
    expect(fetchMock).toHaveBeenCalledWith(`/api/research-runs/${researchRunId}`, {
      credentials: "include",
    });
  });

  it("surfaces a not-found run as a ResearchApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Research run was not found." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(getResearchRun("missing-id")).rejects.toMatchObject({
      message: "Research run was not found.",
      status: 404,
    });
  });
});

describe("private knowledge API", () => {
  const document = {
    id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
    tenant_id: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
    uploaded_by_user_id: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
    filename: "architecture.md",
    media_type: "text/markdown" as const,
    byte_size: 128,
    content_sha256: "a".repeat(64),
    status: "ready" as const,
    error_message: null,
    created_at: "2026-08-05T12:00:00Z",
    updated_at: "2026-08-05T12:00:00Z",
    indexed_at: "2026-08-05T12:00:00Z",
  };

  it("lists documents using the session cookie", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([document]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listKnowledgeDocuments()).resolves.toEqual([document]);
    expect(fetchMock).toHaveBeenCalledWith("/api/documents", {
      credentials: "include",
    });
  });

  it("uploads multipart content without forcing a JSON content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(document), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["trusted evidence"], "architecture.md", {
      type: "text/markdown",
    });

    await uploadKnowledgeDocument(file);

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.method).toBe("POST");
    expect(request.credentials).toBe("include");
    expect(request.body).toBeInstanceOf(FormData);
    expect((request.body as FormData).get("file")).toBe(file);
  });

  it("deletes only the selected tenant document", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteKnowledgeDocument(document.id);

    expect(fetchMock).toHaveBeenCalledWith(`/api/documents/${document.id}`, {
      method: "DELETE",
      credentials: "include",
    });
  });
});
