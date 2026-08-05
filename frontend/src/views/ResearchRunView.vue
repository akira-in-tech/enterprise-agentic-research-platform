<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed, nextTick, watch } from "vue";
import { useRouter } from "vue-router";

import ResearchDetail from "../components/ResearchDetail.vue";
import { getResearchRun } from "../lib/research-api";
import { useResearchStore } from "../stores/research";
import { useWorkspaceStore } from "../stores/workspace";
import type { RecentResearchRun } from "../types/research";

const props = defineProps<{ id: string }>();

const router = useRouter();
const researchStore = useResearchStore();
const workspaceStore = useWorkspaceStore();

const localRun = computed(() => researchStore.getRunById(props.id));

const { data: fetchedRun, isFetching: hydrating, isError: hydrationFailed } = useQuery({
  queryKey: ["research-run", () => props.id],
  queryFn: () => getResearchRun(props.id, workspaceStore.workspace),
  enabled: computed(() => !localRun.value && workspaceStore.isConfigured()),
  retry: false,
});

const currentRun = computed<RecentResearchRun | undefined>(() => {
  if (localRun.value) return localRun.value;

  if (fetchedRun.value) {
    const run = fetchedRun.value;
    return {
      id: run.research_run_id,
      query: run.query,
      provider: run.llm_provider === "anthropic" ? "claude" : "qwen",
      status: run.status,
      message: run.error_message ?? run.route_reason ?? run.status,
      updatedAt: run.completed_at ?? run.started_at ?? run.created_at,
      eventsUrl: `/research-runs/${run.research_run_id}/events`,
      reportUrl: `/research-runs/${run.research_run_id}/report`,
    };
  }

  return undefined;
});

watch(
  currentRun,
  (run, previousRun) => {
    if (!run || run.id === previousRun?.id) return;

    researchStore.stopObserving();
    researchStore.replaceRun(run);
    researchStore.viewRun(run);
    window.scrollTo({ top: 0, behavior: "smooth" });
  },
  { immediate: true },
);

async function goBack(): Promise<void> {
  researchStore.resetActiveRun();
  await router.push({ name: "home" });
  await nextTick();
  document.querySelector<HTMLTextAreaElement>("#research-question")?.focus();
}

async function retry(): Promise<void> {
  if (currentRun.value) researchStore.prefillRetry(currentRun.value);
  researchStore.resetActiveRun();
  await router.push({ name: "home" });
}
</script>

<template>
  <ResearchDetail
    v-if="currentRun"
    :run="currentRun"
    :progress="researchStore.progress"
    :report="researchStore.report"
    :loading-report="researchStore.loadingReport"
    :operational-issue="researchStore.operationalIssue"
    @back="goBack"
    @cancel="researchStore.cancelRun(currentRun)"
    @retry="retry"
    @retry-issue="researchStore.retryOperationalIssue(currentRun)"
    @dismiss-issue="researchStore.operationalIssue = null"
  />

  <main v-else id="main" class="detail-page" tabindex="-1">
    <p v-if="hydrating" aria-live="polite">Loading research run…</p>
    <template v-else-if="hydrationFailed">
      <p role="alert">This research run could not be found.</p>
      <router-link to="/">Back to research</router-link>
    </template>
  </main>
</template>
