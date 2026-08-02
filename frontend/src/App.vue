<script setup lang="ts">
import { PhArrowRight, PhLockKey, PhShieldCheck } from "@phosphor-icons/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

import AgentWorkflow from "./components/AgentWorkflow.vue";
import AppHeader from "./components/AppHeader.vue";
import OperationalNotice from "./components/OperationalNotice.vue";
import ProviderComparison from "./components/ProviderComparison.vue";
import RecentResearchList from "./components/RecentResearchList.vue";
import ResearchComposer from "./components/ResearchComposer.vue";
import ResearchDetail from "./components/ResearchDetail.vue";
import WorkspaceDialog from "./components/WorkspaceDialog.vue";
import { createDesignPreviewReport, createDesignPreviewRuns } from "./lib/design-fixtures";
import { loadResearchHistory, saveResearchHistory } from "./lib/history";
import { defaultProvider, enabledProviders } from "./lib/provider-config";
import {
  createResearchJob,
  getApiHealth,
  getResearchReport,
  ResearchApiError,
  streamResearchProgress,
} from "./lib/research-api";
import type {
  RecentResearchRun,
  OperationalIssue,
  ResearchProgressRecord,
  ResearchReport,
  UserFacingProvider,
  WorkspaceContext,
} from "./types/research";

const WORKSPACE_KEY = "evident.workspace.v1";
const THEME_KEY = "evident.theme.v1";
const designPreview =
  import.meta.env.DEV && new URLSearchParams(window.location.search).has("design-preview");
const designPreviewState = designPreview ? new URLSearchParams(window.location.search).get("state") : null;

const query = ref("");
const provider = ref<UserFacingProvider>(defaultProvider);
const submitting = ref(false);
const recentRuns = ref<RecentResearchRun[]>([]);
const selectedRun = ref<RecentResearchRun | null>(null);
const progress = ref<ResearchProgressRecord | null>(null);
const report = ref<ResearchReport | null>(null);
const loadingReport = ref(false);
const workspaceOpen = ref(false);
const announcement = ref("");
const darkMode = ref(false);
const apiStatus = ref<"checking" | "online" | "offline">("checking");
const operationalIssue = ref<OperationalIssue | null>(null);
const workspace = ref<WorkspaceContext>({
  tenantId: import.meta.env.VITE_TENANT_ID ?? "",
  userId: import.meta.env.VITE_USER_ID ?? "",
});
let progressAbortController: AbortController | null = null;

onMounted(() => {
  recentRuns.value = loadResearchHistory();

  if (designPreview) {
    recentRuns.value = createDesignPreviewRuns();
    query.value =
      "Evaluate event streaming architectures for a real-time fraud detection platform handling 200K events/sec.";
    apiStatus.value = "online";
    workspace.value = {
      tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
      userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
    };
    applyDesignPreviewState();
  }

  const savedWorkspace = localStorage.getItem(WORKSPACE_KEY);
  if (savedWorkspace) {
    try {
      workspace.value = JSON.parse(savedWorkspace) as WorkspaceContext;
    } catch {
      localStorage.removeItem(WORKSPACE_KEY);
    }
  }

  darkMode.value = localStorage.getItem(THEME_KEY) === "dark";
  applyTheme();
  if (!designPreview) {
    void getApiHealth().then((available) => {
      apiStatus.value = available ? "online" : "offline";
    });
  }
});

function applyDesignPreviewState(): void {
  if (designPreviewState === "redis") {
    operationalIssue.value = {
      kind: "redis_unavailable",
      title: "Redis is temporarily unavailable",
      message: "The request was not started, so there is no duplicate job. Reconnect Redis and try again.",
      actionLabel: "Try again",
    };
  } else if (designPreviewState === "sse") {
    operationalIssue.value = {
      kind: "sse_disconnected",
      title: "Live updates disconnected",
      message: "The durable job may still be running. Reconnect to resume progress without starting another job.",
      actionLabel: "Reconnect",
    };
  } else if (designPreviewState === "failed") {
    operationalIssue.value = {
      kind: "job_failed",
      title: "Research job failed",
      message: "The provider stopped before a report was produced. Your previous results remain available.",
      actionLabel: "Try again",
    };
  }
}

onBeforeUnmount(() => progressAbortController?.abort());

function applyTheme(): void {
  document.documentElement.dataset.theme = darkMode.value ? "dark" : "light";
  document.documentElement.style.colorScheme = darkMode.value ? "dark" : "light";
}

function toggleTheme(): void {
  darkMode.value = !darkMode.value;
  localStorage.setItem(THEME_KEY, darkMode.value ? "dark" : "light");
  applyTheme();
}

function persistRuns(): void {
  saveResearchHistory(recentRuns.value);
}

function replaceRun(next: RecentResearchRun): void {
  recentRuns.value = [next, ...recentRuns.value.filter((run) => run.id !== next.id)];
  selectedRun.value = next;
  persistRuns();
}

function workspaceIsConfigured(): boolean {
  return workspace.value.tenantId.trim().length > 0;
}

async function submitResearch(): Promise<void> {
  const normalizedQuery = query.value.trim();
  if (!normalizedQuery || submitting.value) return;

  if (!workspaceIsConfigured()) {
    announcement.value = "Connect a tenant workspace before starting research.";
    workspaceOpen.value = true;
    return;
  }

  submitting.value = true;
  operationalIssue.value = null;
  announcement.value = "Submitting research request.";

  try {
    const job = await createResearchJob(normalizedQuery, provider.value, workspace.value);
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
    await observeRun(run);
  } catch (error) {
    const message = error instanceof ResearchApiError ? error.message : "The research request could not be started.";
    const redisUnavailable = /redis|rate limit|cache/i.test(message);
    operationalIssue.value = redisUnavailable
      ? {
          kind: "redis_unavailable",
          title: "Redis is temporarily unavailable",
          message: "The request was not started, so there is no duplicate job. Reconnect Redis and try again.",
          actionLabel: "Try again",
        }
      : {
          kind: "job_failed",
          title: "Research could not start",
          message,
          actionLabel: "Try again",
        };
    announcement.value = message;
  } finally {
    submitting.value = false;
  }
}

async function observeRun(run: RecentResearchRun): Promise<void> {
  if (!run.eventsUrl) return;

  progressAbortController?.abort();
  progressAbortController = new AbortController();

  try {
    await streamResearchProgress(
      run.eventsUrl,
      workspace.value,
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
      progressAbortController.signal,
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
      message: "The durable job may still be running. Reconnect to resume progress without starting another job.",
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
    report.value = await getResearchReport(run.reportUrl, workspace.value);
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
        message: "The answer is available, but one or more claims need stronger source coverage before approval.",
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
      message: "The completed job is safe. Retry loading the report without rerunning the research.",
      actionLabel: "Load report",
    };
    announcement.value = message;
  } finally {
    loadingReport.value = false;
  }
}

function selectRun(run: RecentResearchRun): void {
  selectedRun.value = run;
  progress.value = null;
  report.value = null;
  window.scrollTo({ top: 0, behavior: "smooth" });

  if (designPreview) {
    if (run.status === "completed") {
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
          message: "The answer is available, but one claim needs stronger source coverage before approval.",
          actionLabel: "Review evidence",
        };
      } else if (designPreviewState === "report") {
        report.value = null;
        operationalIssue.value = {
          kind: "report_unavailable",
          title: "Report is temporarily unavailable",
          message: "The completed job is safe. Retry loading the report without rerunning the research.",
          actionLabel: "Load report",
        };
      }
    }
    return;
  }

  if ((run.status === "queued" || run.status === "running") && run.eventsUrl) {
    void observeRun(run);
  } else if (run.status === "completed" && run.reportUrl) {
    void loadReport(run);
  }
}

function startNewResearch(): void {
  progressAbortController?.abort();
  selectedRun.value = null;
  progress.value = null;
  report.value = null;
  operationalIssue.value = null;
  window.scrollTo({ top: 0, behavior: "smooth" });
  requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>("#research-question")?.focus());
}

function retrySelected(): void {
  if (!selectedRun.value) return;
  query.value = selectedRun.value.query;
  provider.value = selectedRun.value.provider;
  startNewResearch();
}

function retryOperationalIssue(): void {
  if (!operationalIssue.value) return;

  if (operationalIssue.value.kind === "sse_disconnected" && selectedRun.value) {
    void observeRun(selectedRun.value);
  } else if (
    (operationalIssue.value.kind === "report_unavailable" ||
      operationalIssue.value.kind === "citation_revision_required") &&
    selectedRun.value
  ) {
    void loadReport(selectedRun.value);
  } else {
    retrySelected();
  }
}

function saveWorkspace(next: WorkspaceContext): void {
  workspace.value = next;
  localStorage.setItem(WORKSPACE_KEY, JSON.stringify(next));
  workspaceOpen.value = false;
  announcement.value = "Workspace context saved.";
}
</script>

<template>
  <a v-if="!designPreview" class="skip-link" href="#main">Skip to main content</a>
  <div class="app-shell">
    <AppHeader
      :dark-mode="darkMode"
      :api-status="apiStatus"
      :workspace-configured="workspaceIsConfigured()"
      workspace-name="Acme Analytics"
      @new-research="startNewResearch"
      @show-recent="startNewResearch"
      @toggle-theme="toggleTheme"
      @open-workspace="workspaceOpen = true"
    />

    <ResearchDetail
      v-if="selectedRun"
      :run="selectedRun"
      :progress="progress"
      :report="report"
      :loading-report="loadingReport"
      :operational-issue="operationalIssue"
      @back="startNewResearch"
      @retry="retrySelected"
      @retry-issue="retryOperationalIssue"
      @dismiss-issue="operationalIssue = null"
    />

    <main v-else id="main" class="home-page" tabindex="-1">
      <section class="hero-section" aria-labelledby="hero-title">
        <div class="hero-intro">
          <p class="hero-eyebrow">Trusted research workspace</p>
          <h1 id="hero-title">A <em>research</em><br />workspace for<br />answers that<br />hold up.</h1>
          <span class="hero-rule" aria-hidden="true"></span>
          <p class="hero-copy">Plan the work. Inspect the evidence.<br />Share a report with every source attached.</p>
          <ul class="trust-list" aria-label="Research guarantees">
            <li><PhShieldCheck :size="21" /> Sources remain inspectable</li>
            <li><PhLockKey :size="21" /> Your data stays tenant-scoped and is never used for training.</li>
          </ul>
        </div>

        <div class="research-start-panel">
          <p class="start-panel-label">Start new research</p>

          <OperationalNotice
            v-if="operationalIssue"
            :issue="operationalIssue"
            @action="retryOperationalIssue"
            @dismiss="operationalIssue = null"
          />

          <ResearchComposer
            v-model:query="query"
            v-model:provider="provider"
            :enabled-providers="enabledProviders"
            :submitting="submitting"
            @submit="submitResearch"
          />

          <ProviderComparison
            v-model="provider"
            :enabled-providers="enabledProviders"
            :disabled="submitting"
          />

          <button
            v-if="!workspaceIsConfigured()"
            class="workspace-notice"
            type="button"
            @click="workspaceOpen = true"
          >
            <span><PhLockKey :size="16" /> Connect your tenant workspace to run the real pipeline</span>
            <PhArrowRight :size="16" />
          </button>
        </div>
      </section>

      <AgentWorkflow />

      <RecentResearchList :runs="recentRuns" @select="selectRun" />
    </main>

    <footer class="app-footer">
      <span>All research and sources are scoped to Acme Analytics.</span>
      <span>You control access. You own the results.</span>
    </footer>
  </div>

  <WorkspaceDialog
    :open="workspaceOpen"
    :workspace="workspace"
    @close="workspaceOpen = false"
    @save="saveWorkspace"
  />

  <p class="sr-only" aria-live="polite">{{ announcement }}</p>
</template>
