import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecentResearchRun, ResearchReport, ResearchReportSource } from "../types/research";
import ResearchDetail from "./ResearchDetail.vue";

afterEach(() => vi.unstubAllGlobals());

const run: RecentResearchRun = {
  id: "run-1",
  query: "Compare event delivery architectures.",
  provider: "qwen",
  status: "completed",
  message: "Report ready",
  updatedAt: "2026-08-01T12:00:00Z",
};

const baseSource: ResearchReportSource = {
  source_id: "source-1",
  origin: "web",
  title: "Transactional outbox reference",
  locator: "https://example.com/outbox",
  provider: "tavily",
  relevance: 0.98,
  content_quality: 0.95,
  traceability: 1,
  overall_score: 0.97,
  cited: true,
  source_type: "web",
  authors: [],
  year: null,
  venue: null,
};

const report: ResearchReport = {
  report_id: "report-1",
  research_run_id: "run-1",
  content: "Use an outbox when atomic database writes matter most.",
  workflow_status: "report_completed",
  citation_valid: true,
  citation_coverage: 0.94,
  reflection_status: "approved",
  reflection_reasons: [],
  reflection_attempts: 1,
  created_at: "2026-08-01T12:00:00Z",
  sources: [baseSource],
};

describe("ResearchDetail", () => {
  it("shows the conclusion and quality before keeping evidence collapsed", async () => {
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report,
        loadingReport: false,
        operationalIssue: null,
      },
    });

    expect(wrapper.text()).toContain("Research conclusion");
    expect(wrapper.text()).toContain("Why this answer holds up");
    expect(wrapper.find("#evidence-panel").exists()).toBe(false);

    const toggle = wrapper.get(".evidence-toggle");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    await toggle.trigger("click");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(wrapper.get("#evidence-panel").text()).toContain("Transactional outbox reference");
  });

  it("renders report markdown as real HTML instead of raw source", () => {
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report: {
          ...report,
          content: "# Outbox pattern\n\nUse an outbox when **atomic** writes matter most.",
        },
        loadingReport: false,
        operationalIssue: null,
      },
    });

    const content = wrapper.get(".report-content");
    expect(content.find("h1").text()).toBe("Outbox pattern");
    expect(content.find("strong").text()).toBe("atomic");
    expect(content.html()).not.toContain("# Outbox pattern");
  });

  it("turns citation markers into numbered links that jump to their source", async () => {
    const citedReport: ResearchReport = {
      ...report,
      content: "Outbox writes stay atomic [WEB-0123456789ABCDEF].",
      sources: [{ ...baseSource, source_id: "WEB-0123456789ABCDEF" }],
    };
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report: citedReport,
        loadingReport: false,
        operationalIssue: null,
      },
      attachTo: document.body,
    });

    const citationLink = wrapper.get('a[data-source-id="WEB-0123456789ABCDEF"]');
    expect(citationLink.text()).toBe("1");

    expect(wrapper.find("#evidence-panel").exists()).toBe(false);
    await citationLink.trigger("click");

    expect(wrapper.get("#evidence-panel").attributes("id")).toBe("evidence-panel");
    expect(wrapper.find("#source-WEB-0123456789ABCDEF.source-card-highlighted").exists()).toBe(
      true,
    );

    wrapper.unmount();
  });

  it("leaves an unmatched citation marker as plain text", () => {
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report: {
          ...report,
          content: "This claim has no matching source [WEB-FFFFFFFFFFFFFFFF].",
        },
        loadingReport: false,
        operationalIssue: null,
      },
    });

    expect(wrapper.get(".report-content").text()).toContain("[WEB-FFFFFFFFFFFFFFFF]");
    expect(wrapper.find("a[data-source-id]").exists()).toBe(false);
  });

  it("surfaces citation revision as a first-class report state", () => {
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report: {
          ...report,
          citation_valid: false,
          reflection_status: "revise",
          reflection_reasons: ["Claim needs a stronger source."],
        },
        loadingReport: false,
        operationalIssue: {
          kind: "citation_revision_required",
          title: "Citation revision required",
          message: "One claim needs stronger source coverage.",
          actionLabel: "Review evidence",
        },
      },
    });

    expect(wrapper.text()).toContain("Citation revision required");
    expect(wrapper.text()).toContain("Revision required");
  });

  it("downloads the report as a file when Download is clicked", async () => {
    // jsdom does not implement real anchor navigation; the component clicks a
    // temporary <a download> element to trigger the browser's save dialog,
    // which jsdom would otherwise try (and fail) to actually navigate to.
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ storage_key: "tenants/x/report-exports/y/report.md" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("# Report content", {
          status: 200,
          headers: { "Content-Type": "text/markdown; charset=utf-8" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report,
        loadingReport: false,
        operationalIssue: null,
      },
    });

    await wrapper.get(".download-button").trigger("click");
    await wrapper.get('[role="option"]').trigger("click");
    await new Promise((resolve) => setTimeout(resolve));
    await wrapper.vm.$nextTick();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(wrapper.find(".field-error").exists()).toBe(false);
    expect(clickSpy).toHaveBeenCalledOnce();
    clickSpy.mockRestore();
  });

  it("shows an inline error when the report download fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "Report export storage is temporarily unavailable." }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );
    const wrapper = mount(ResearchDetail, {
      props: {
        run,
        progress: null,
        report,
        loadingReport: false,
        operationalIssue: null,
      },
    });

    await wrapper.get(".download-button").trigger("click");
    await wrapper.get('[role="option"]').trigger("click");
    await new Promise((resolve) => setTimeout(resolve));
    await wrapper.vm.$nextTick();

    expect(wrapper.get(".field-error").text()).toContain(
      "Report export storage is temporarily unavailable.",
    );
  });

  it("offers cancellation only while a durable job is active", async () => {
    const wrapper = mount(ResearchDetail, {
      props: {
        run: {
          ...run,
          status: "running",
          message: "Research workflow is running.",
        },
        progress: null,
        report: null,
        loadingReport: false,
        operationalIssue: null,
      },
    });

    await wrapper.get("button.secondary-button").trigger("click");

    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
