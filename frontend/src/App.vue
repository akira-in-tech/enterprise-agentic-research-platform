<script setup lang="ts">
import { PhArrowRight, PhSparkle } from "@phosphor-icons/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

import AppHeader from "./components/AppHeader.vue";
import RecentResearchList from "./components/RecentResearchList.vue";
import ResearchComposer from "./components/ResearchComposer.vue";
import ResearchDetail from "./components/ResearchDetail.vue";
import WorkspaceDialog from "./components/WorkspaceDialog.vue";
import { createDesignPreviewRuns } from "./lib/design-fixtures";
import { loadResearchHistory, saveResearchHistory } from "./lib/history";
import {
  createResearchJob,
  getApiHealth,
  getResearchReport,
  ResearchApiError,
  streamResearchProgress,
} from "./lib/research-api";
import type {
  RecentResearchRun,
  ResearchProgressRecord,
  ResearchReport,
  UserFacingProvider,
  WorkspaceContext,
} from "./types/research";

const WORKSPACE_KEY = "evident.workspace.v1";
const THEME_KEY = "evident.theme.v1";
const designPreview =
  import.meta.env.DEV && new URLSearchParams(window.location.search).has("design-preview");

const query = ref("");
const provider = ref<UserFacingProvider>("qwen");
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
    announcement.value =
      error instanceof ResearchApiError ? error.message : "The research request could not be started.";
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
    const failed: RecentResearchRun = {
      ...run,
      status: "failed",
      message: error instanceof Error ? error.message : "Progress connection failed",
      updatedAt: new Date().toISOString(),
    };
    replaceRun(failed);
    announcement.value = failed.message;
  }
}

async function loadReport(run: RecentResearchRun): Promise<void> {
  if (!run.reportUrl) return;

  loadingReport.value = true;
  try {
    report.value = await getResearchReport(run.reportUrl, workspace.value);
    replaceRun({
      ...run,
      status: "completed",
      message: "Report ready",
      citationCoverage: report.value.citation_coverage,
      updatedAt: report.value.created_at,
    });
    announcement.value = "Research report is ready.";
  } catch (error) {
    announcement.value = error instanceof Error ? error.message : "The report could not be loaded.";
  } finally {
    loadingReport.value = false;
  }
}

function selectRun(run: RecentResearchRun): void {
  selectedRun.value = run;
  progress.value = null;
  report.value = null;
  window.scrollTo({ top: 0, behavior: "smooth" });

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
  window.scrollTo({ top: 0, behavior: "smooth" });
  requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>("#research-question")?.focus());
}

function retrySelected(): void {
  if (!selectedRun.value) return;
  query.value = selectedRun.value.query;
  provider.value = selectedRun.value.provider;
  startNewResearch();
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
      @back="startNewResearch"
      @retry="retrySelected"
    />

    <main v-else id="main" class="home-page" tabindex="-1">
      <section class="hero-section" aria-labelledby="hero-title">
        <h1 id="hero-title">Research with evidence,<br /><span>not guesses.</span></h1>
        <p class="hero-copy">
          Ask complex questions. Get grounded, source-traceable answers.
        </p>

        <ResearchComposer
          v-model:query="query"
          v-model:provider="provider"
          :submitting="submitting"
          @submit="submitResearch"
        />

        <button v-if="!workspaceIsConfigured()" class="workspace-notice" type="button" @click="workspaceOpen = true">
          <span><PhSparkle :size="16" /> Connect your tenant workspace to run the real pipeline</span>
          <PhArrowRight :size="16" />
        </button>
      </section>

      <RecentResearchList :runs="recentRuns" @select="selectRun" />
    </main>

    <footer class="app-footer">
      <span>Evident research console</span>
      <span>Tenant-scoped · source-traceable · provider-explicit</span>
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
