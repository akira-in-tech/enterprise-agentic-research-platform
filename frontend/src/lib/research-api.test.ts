import { afterEach, describe, expect, it, vi } from "vitest";

import {
  cancelResearchJob,
  deleteKnowledgeDocument,
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
  it("cancels one run with tenant-scoped headers", async () => {
    const workspace = {
      tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
      userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
    };
    const researchRunId = "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ research_run_id: researchRunId, status: "cancelled" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(cancelResearchJob(researchRunId, workspace)).resolves.toEqual({
      research_run_id: researchRunId,
      status: "cancelled",
    });
    expect(fetchMock).toHaveBeenCalledWith(`/api/research-runs/${researchRunId}/cancel`, {
      method: "POST",
      headers: {
        "X-Tenant-ID": workspace.tenantId,
        "X-User-ID": workspace.userId,
        "Content-Type": "application/json",
      },
    });
  });
});

describe("private knowledge API", () => {
  const workspace = {
    tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
    userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
  };
  const document = {
    id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
    tenant_id: workspace.tenantId,
    uploaded_by_user_id: workspace.userId,
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

  it("lists documents with tenant and user scope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([document]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listKnowledgeDocuments(workspace)).resolves.toEqual([document]);
    expect(fetchMock).toHaveBeenCalledWith("/api/documents", {
      headers: {
        "X-Tenant-ID": workspace.tenantId,
        "X-User-ID": workspace.userId,
      },
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

    await uploadKnowledgeDocument(file, workspace);

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.method).toBe("POST");
    expect(request.headers).toEqual({
      "X-Tenant-ID": workspace.tenantId,
      "X-User-ID": workspace.userId,
    });
    expect(request.body).toBeInstanceOf(FormData);
    expect((request.body as FormData).get("file")).toBe(file);
  });

  it("deletes only the selected tenant document", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteKnowledgeDocument(document.id, workspace);

    expect(fetchMock).toHaveBeenCalledWith(`/api/documents/${document.id}`, {
      method: "DELETE",
      headers: {
        "X-Tenant-ID": workspace.tenantId,
        "X-User-ID": workspace.userId,
      },
    });
  });
});
