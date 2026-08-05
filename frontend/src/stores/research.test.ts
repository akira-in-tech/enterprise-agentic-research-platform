import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useResearchStore } from "./research";
import { useWorkspaceStore } from "./workspace";

const workspace = {
  tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
  userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
};

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  useWorkspaceStore().setForPreview(workspace);
});

afterEach(() => vi.unstubAllGlobals());

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("submitResearch", () => {
  it("does nothing when the workspace is not configured", async () => {
    useWorkspaceStore().setForPreview({ tenantId: "", userId: "" });
    const store = useResearchStore();
    store.query = "Compare HTTP/2 and HTTP/3.";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const run = await store.submitResearch();

    expect(run).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(store.announcement).toContain("Connect a tenant workspace");
  });

  it("creates a job, records the run, and clears the composer", async () => {
    const store = useResearchStore();
    store.query = "Compare HTTP/2 and HTTP/3.";
    // submitResearch() fires observeRun() in the background without awaiting
    // it (so navigation is not blocked for the whole job duration), so the
    // mock must also answer its /events call: an immediately closed stream
    // lets that background call settle deterministically.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/events")) {
          return new Response(
            new ReadableStream({
              start(controller) {
                controller.close();
              },
            }),
            { status: 200 },
          );
        }
        return jsonResponse({
          research_run_id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
          status: "queued",
          progress_url: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/progress",
          events_url: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/events",
          report_url: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/report",
        });
      }),
    );

    const run = await store.submitResearch();
    await flushPromises();

    expect(run?.id).toBe("89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589");
    expect(store.query).toBe("");
    expect(store.recentRuns[0]?.id).toBe("89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589");
    expect(store.recentRuns[0]?.status).toBe("queued");
  });

  it("surfaces a Redis-flavored failure as a distinct operational issue", async () => {
    const store = useResearchStore();
    store.query = "Compare HTTP/2 and HTTP/3.";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Research rate limiting is unavailable." }, 503),
      ),
    );

    const run = await store.submitResearch();

    expect(run).toBeNull();
    expect(store.operationalIssue?.kind).toBe("redis_unavailable");
  });

  it("is a no-op for a blank or already-submitting query", async () => {
    const store = useResearchStore();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    store.query = "   ";
    expect(await store.submitResearch()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("loadReport", () => {
  it("loads an approved report and marks the run completed", async () => {
    const store = useResearchStore();
    const run = {
      id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
      query: "Compare HTTP/2 and HTTP/3.",
      provider: "claude" as const,
      status: "running" as const,
      message: "In progress",
      updatedAt: "2026-08-05T12:00:00Z",
      reportUrl: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/report",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          report_id: "d38f3124-7d77-4bda-b711-10ca1e39f460",
          research_run_id: run.id,
          content: "HTTP/3 evidence.",
          workflow_status: "research_report_completed",
          citation_valid: true,
          citation_coverage: 0.9,
          reflection_status: "approved",
          reflection_reasons: [],
          reflection_attempts: 1,
          created_at: "2026-08-05T12:01:00Z",
          sources: [],
        }),
      ),
    );

    await store.loadReport(run);

    expect(store.report?.reflection_status).toBe("approved");
    expect(store.operationalIssue).toBeNull();
    expect(store.getRunById(run.id)?.status).toBe("completed");
  });

  it("flags a revision-required report as an operational issue", async () => {
    const store = useResearchStore();
    const run = {
      id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
      query: "Compare HTTP/2 and HTTP/3.",
      provider: "claude" as const,
      status: "running" as const,
      message: "In progress",
      updatedAt: "2026-08-05T12:00:00Z",
      reportUrl: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/report",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          report_id: "d38f3124-7d77-4bda-b711-10ca1e39f460",
          research_run_id: run.id,
          content: "HTTP/3 evidence.",
          workflow_status: "research_report_revision_required",
          citation_valid: false,
          citation_coverage: 0.4,
          reflection_status: "revise",
          reflection_reasons: ["Add a stronger primary source."],
          reflection_attempts: 2,
          created_at: "2026-08-05T12:01:00Z",
          sources: [],
        }),
      ),
    );

    await store.loadReport(run);

    expect(store.operationalIssue?.kind).toBe("citation_revision_required");
  });
});

describe("cancelRun", () => {
  it("cancels an active run and publishes a terminal snapshot", async () => {
    const store = useResearchStore();
    const run = {
      id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
      query: "Compare HTTP/2 and HTTP/3.",
      provider: "claude" as const,
      status: "running" as const,
      message: "In progress",
      updatedAt: "2026-08-05T12:00:00Z",
    };
    store.replaceRun(run);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ research_run_id: run.id, status: "cancelled" })),
    );

    await store.cancelRun(run);

    expect(store.progress?.status).toBe("cancelled");
    expect(store.getRunById(run.id)?.status).toBe("cancelled");
  });

  it("does nothing for an already-terminal run", async () => {
    const store = useResearchStore();
    const run = {
      id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
      query: "Compare HTTP/2 and HTTP/3.",
      provider: "claude" as const,
      status: "completed" as const,
      message: "Report ready",
      updatedAt: "2026-08-05T12:00:00Z",
    };
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await store.cancelRun(run);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("run bookkeeping", () => {
  it("replaces and looks up runs by id, keeping the most recent first", () => {
    const store = useResearchStore();
    store.replaceRun({
      id: "a",
      query: "First",
      provider: "claude",
      status: "completed",
      message: "Report ready",
      updatedAt: "2026-08-05T12:00:00Z",
    });
    store.replaceRun({
      id: "b",
      query: "Second",
      provider: "qwen",
      status: "running",
      message: "In progress",
      updatedAt: "2026-08-05T12:01:00Z",
    });

    expect(store.recentRuns.map((run) => run.id)).toEqual(["b", "a"]);
    expect(store.getRunById("a")?.query).toBe("First");
    expect(store.getRunById("missing")).toBeUndefined();
  });

  it("prefills the composer from a run for retry", () => {
    const store = useResearchStore();

    store.prefillRetry({
      id: "a",
      query: "Compare HTTP/2 and HTTP/3.",
      provider: "qwen",
      status: "failed",
      message: "Provider error",
      updatedAt: "2026-08-05T12:00:00Z",
    });

    expect(store.query).toBe("Compare HTTP/2 and HTTP/3.");
    expect(store.provider).toBe("qwen");
  });

  it("resets progress, report, and operational issue for a fresh view", () => {
    const store = useResearchStore();
    store.progress = {
      research_run_id: "a",
      status: "running",
      message: "In progress",
      updated_at: "2026-08-05T12:00:00Z",
      workflow_status: null,
      error_message: null,
    };
    store.operationalIssue = {
      kind: "job_failed",
      title: "Research could not start",
      message: "boom",
    };

    store.resetActiveRun();

    expect(store.progress).toBeNull();
    expect(store.report).toBeNull();
    expect(store.operationalIssue).toBeNull();
  });
});
