import { defineStore } from "pinia";
import { ref } from "vue";

import { createDesignPreviewReport, createDesignPreviewRuns } from "../lib/design-fixtures";
import { loadResearchHistory, saveResearchHistory } from "../lib/history";
import { defaultProvider } from "../lib/provider-config";
import {
  cancelResearchJob,
  createResearchJob,
  getApiHealth,
  getResearchReport,
  ResearchApiError,
  streamResearchProgress,
} from "../lib/research-api";
import type {
  OperationalIssue,
  RecentResearchRun,
  ResearchProgressRecord,
  ResearchReport,
  UserFacingProvider,
} from "../types/research";
import { useAuthStore } from "./auth";

export const useResearchStore = defineStore("research", () => {
  const query = ref("");
  const provider = ref<UserFacingProvider>(defaultProvider);
  const submitting = ref(false);
  const recentRuns = ref<RecentResearchRun[]>([]);
  const progress = ref<ResearchProgressRecord | null>(null);
  const report = ref<ResearchReport | null>(null);
  const loadingReport = ref(false);
  const announcement = ref("");
  const apiStatus = ref<"checking" | "online" | "offline">("checking");
  const operationalIssue = ref<OperationalIssue | null>(null);

  const designPreview =
    import.meta.env.DEV && new URLSearchParams(window.location.search).has("design-preview");
  const designPreviewState = designPreview
    ? new URLSearchParams(window.location.search).get("state")
    : null;

  let progressAbortController: AbortController | null = null;

  function hydrate(): void {
    recentRuns.value = loadResearchHistory();

    if (designPreview) {
      recentRuns.value = createDesignPreviewRuns();
      query.value =
        "Evaluate event streaming architectures for a real-time fraud detection platform handling 200K events/sec.";
      apiStatus.value = "online";
      useAuthStore().setForPreview({
        user: {
          id: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
          email: "preview@acme.example",
          display_name: "Preview User",
        },
        tenant: {
          id: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
          name: "Acme Analytics",
          slug: "acme-analytics-preview",
        },
      });
      return;
    }

    void getApiHealth().then((available) => {
      apiStatus.value = available ? "online" : "offline";
    });
  }

  function applyDesignPreviewIssue(): void {
    if (designPreviewState === "redis") {
      operationalIssue.value = {
        kind: "redis_unavailable",
        title: "Redis is temporarily unavailable",
        message:
          "The request was not started, so there is no duplicate job. Reconnect Redis and try again.",
        actionLabel: "Try again",
      };
    } else if (designPreviewState === "sse") {
      operationalIssue.value = {
        kind: "sse_disconnected",
        title: "Live updates disconnected",
        message:
          "The durable job may still be running. Reconnect to resume progress without starting another job.",
        actionLabel: "Reconnect",
      };
    } else if (designPreviewState === "failed") {
      operationalIssue.value = {
        kind: "job_failed",
        title: "Research job failed",
        message:
          "The provider stopped before a report was produced. Your previous results remain available.",
        actionLabel: "Try again",
      };
    }
  }

  function persistRuns(): void {
    saveResearchHistory(recentRuns.value);
  }

  function replaceRun(next: RecentResearchRun): void {
    recentRuns.value = [next, ...recentRuns.value.filter((run) => run.id !== next.id)];
    persistRuns();
  }

  function getRunById(id: string): RecentResearchRun | undefined {
    return recentRuns.value.find((run) => run.id === id);
  }

  function stopObserving(): void {
    progressAbortController?.abort();
  }

  function resetActiveRun(): void {
    stopObserving();
    progress.value = null;
    report.value = null;
    operationalIssue.value = null;
  }

  async function submitResearch(): Promise<RecentResearchRun | null> {
    const normalizedQuery = query.value.trim();
    if (!normalizedQuery || submitting.value) return null;

    if (!useAuthStore().isAuthenticated()) {
      announcement.value = "Sign in before starting research.";
      return null;
    }

    submitting.value = true;
    operationalIssue.value = null;
    announcement.value = "Submitting research request.";

    try {
      const job = await createResearchJob(normalizedQuery, provider.value);
      const run: RecentResearchRun = {
        id: job.research_run_id,
        query: normalizedQuery,
        provider: provider.value,
        status: "queued",
        message: "Request accepted",
        updatedAt: new Date().toISOString(),
        eventsUrl: job.events_url,
        reportUrl: job.report_url,
      };
      replaceRun(run);
      progress.value = null;
      report.value = null;
      query.value = "";
      announcement.value = "Research accepted and running in the background.";
      void observeRun(run);
      return run;
    } catch (error) {
      const message =
        error instanceof ResearchApiError
          ? error.message
          : "The research request could not be started.";
      const redisUnavailable = /redis|rate limit|cache/i.test(message);
      operationalIssue.value = redisUnavailable
        ? {
            kind: "redis_unavailable",
            title: "Redis is temporarily unavailable",
            message:
              "The request was not started, so there is no duplicate job. Reconnect Redis and try again.",
            actionLabel: "Try again",
          }
        : {
            kind: "job_failed",
            title: "Research could not start",
            message,
            actionLabel: "Try again",
          };
      announcement.value = message;
      return null;
    } finally {
      submitting.value = false;
    }
  }

  async function observeRun(initialRun: RecentResearchRun): Promise<void> {
    const eventsUrl = initialRun.eventsUrl;
    if (!eventsUrl) return;

    let run = initialRun;
    progressAbortController?.abort();
    const controller = new AbortController();
    progressAbortController = controller;

    try {
      await streamResearchProgress(
        eventsUrl,
        (record) => {
          progress.value = record;
          const updated: RecentResearchRun = {
            ...run,
            status: record.status,
            message: record.error_message ?? record.message,
            updatedAt: record.updated_at,
          };
          run = updated;
          replaceRun(updated);
          announcement.value = `Research ${record.status}: ${record.message}`;
        },
        controller.signal,
      );

      if (run.status === "completed" && run.reportUrl) {
        await loadReport(run);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      const disconnected: RecentResearchRun = {
        ...run,
        status: run.status === "queued" ? "running" : run.status,
        message: "Live progress disconnected",
        updatedAt: new Date().toISOString(),
      };
      replaceRun(disconnected);
      operationalIssue.value = {
        kind: "sse_disconnected",
        title: "Live updates disconnected",
        message:
          "The durable job may still be running. Reconnect to resume progress without starting another job.",
        actionLabel: "Reconnect",
      };
      announcement.value = "Live progress disconnected. The durable job may still be running.";
    }
  }

  async function loadReport(run: RecentResearchRun): Promise<void> {
    if (!run.reportUrl) return;

    loadingReport.value = true;
    operationalIssue.value = null;
    try {
      report.value = await getResearchReport(run.reportUrl);
      replaceRun({
        ...run,
        status: "completed",
        message: "Report ready",
        citationCoverage: report.value.citation_coverage,
        updatedAt: report.value.created_at,
      });
      if (report.value.reflection_status === "revise") {
        operationalIssue.value = {
          kind: "citation_revision_required",
          title: "Citation revision required",
          message:
            "The answer is available, but one or more claims need stronger source coverage before approval.",
          actionLabel: "Review evidence",
        };
        announcement.value = "Research report requires citation revision.";
      } else {
        announcement.value = "Research report is ready.";
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The report could not be loaded.";
      operationalIssue.value = {
        kind: "report_unavailable",
        title: "Report is temporarily unavailable",
        message:
          "The completed job is safe. Retry loading the report without rerunning the research.",
        actionLabel: "Load report",
      };
      announcement.value = message;
    } finally {
      loadingReport.value = false;
    }
  }

  async function cancelRun(run: RecentResearchRun): Promise<void> {
    if (run.status !== "queued" && run.status !== "running") return;

    try {
      await cancelResearchJob(run.id);
      stopObserving();
      const updatedAt = new Date().toISOString();
      const message = "Research workflow was cancelled.";
      progress.value = {
        research_run_id: run.id,
        status: "cancelled",
        message,
        updated_at: updatedAt,
        workflow_status: null,
        error_message: null,
      };
      replaceRun({
        ...run,
        status: "cancelled",
        message,
        updatedAt,
      });
      announcement.value = "Research cancelled.";
    } catch (error) {
      announcement.value =
        error instanceof Error ? error.message : "Research could not be cancelled.";
    }
  }

  function selectRunForDesignPreview(run: RecentResearchRun): void {
    if (run.status !== "completed") return;

    report.value = createDesignPreviewReport();
    if (designPreviewState === "citation") {
      report.value = {
        ...report.value,
        citation_valid: false,
        reflection_status: "revise",
        reflection_reasons: ["One recommendation needs a stronger primary source."],
      };
      operationalIssue.value = {
        kind: "citation_revision_required",
        title: "Citation revision required",
        message:
          "The answer is available, but one claim needs stronger source coverage before approval.",
        actionLabel: "Review evidence",
      };
    } else if (designPreviewState === "report") {
      report.value = null;
      operationalIssue.value = {
        kind: "report_unavailable",
        title: "Report is temporarily unavailable",
        message:
          "The completed job is safe. Retry loading the report without rerunning the research.",
        actionLabel: "Load report",
      };
    }
  }

  function viewRun(run: RecentResearchRun): void {
    progress.value = null;
    report.value = null;
    operationalIssue.value = null;

    if (designPreview) {
      selectRunForDesignPreview(run);
      return;
    }

    if ((run.status === "queued" || run.status === "running") && run.eventsUrl) {
      void observeRun(run);
    } else if (run.status === "completed" && run.reportUrl) {
      void loadReport(run);
    }
  }

  function prefillRetry(run: RecentResearchRun): void {
    query.value = run.query;
    provider.value = run.provider;
  }

  function retryOperationalIssue(run: RecentResearchRun | undefined): void {
    if (!operationalIssue.value) return;

    if (operationalIssue.value.kind === "sse_disconnected" && run) {
      void observeRun(run);
    } else if (
      (operationalIssue.value.kind === "report_unavailable" ||
        operationalIssue.value.kind === "citation_revision_required") &&
      run
    ) {
      void loadReport(run);
    } else if (run) {
      prefillRetry(run);
    }
  }

  return {
    query,
    provider,
    submitting,
    recentRuns,
    progress,
    report,
    loadingReport,
    announcement,
    apiStatus,
    operationalIssue,
    designPreview,
    designPreviewState,
    hydrate,
    applyDesignPreviewIssue,
    replaceRun,
    getRunById,
    stopObserving,
    resetActiveRun,
    submitResearch,
    observeRun,
    loadReport,
    cancelRun,
    viewRun,
    prefillRetry,
    retryOperationalIssue,
  };
});
