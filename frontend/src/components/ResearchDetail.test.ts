import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { RecentResearchRun, ResearchReport } from "../types/research";
import ResearchDetail from "./ResearchDetail.vue";

const run: RecentResearchRun = {
  id: "run-1",
  query: "Compare event delivery architectures.",
  provider: "qwen",
  status: "completed",
  message: "Report ready",
  updatedAt: "2026-08-01T12:00:00Z",
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
  sources: [
    {
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
    },
  ],
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
