<script setup lang="ts">
import { PhLockKey, PhShieldCheck } from "@phosphor-icons/vue";
import { useRouter } from "vue-router";

import AgentWorkflow from "../components/AgentWorkflow.vue";
import OperationalNotice from "../components/OperationalNotice.vue";
import ProviderComparison from "../components/ProviderComparison.vue";
import RecentResearchList from "../components/RecentResearchList.vue";
import ResearchComposer from "../components/ResearchComposer.vue";
import { enabledProviders } from "../lib/provider-config";
import { useResearchStore } from "../stores/research";
import type { RecentResearchRun } from "../types/research";

const router = useRouter();
const researchStore = useResearchStore();

async function submitResearch(): Promise<void> {
  const run = await researchStore.submitResearch();
  if (run) {
    await router.push({ name: "research-run", params: { id: run.id } });
  }
}

function selectRun(run: RecentResearchRun): void {
  void router.push({ name: "research-run", params: { id: run.id } });
}
</script>

<template>
  <main id="main" class="home-page" tabindex="-1">
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
          v-if="researchStore.operationalIssue"
          :issue="researchStore.operationalIssue"
          @action="researchStore.retryOperationalIssue(undefined)"
          @dismiss="researchStore.operationalIssue = null"
        />

        <ResearchComposer
          v-model:query="researchStore.query"
          v-model:provider="researchStore.provider"
          :enabled-providers="enabledProviders"
          :submitting="researchStore.submitting"
          @submit="submitResearch"
        />

        <ProviderComparison
          v-model="researchStore.provider"
          :enabled-providers="enabledProviders"
          :disabled="researchStore.submitting"
        />
      </div>
    </section>

    <AgentWorkflow />

    <RecentResearchList :runs="researchStore.recentRuns" @select="selectRun" />
  </main>
</template>
