<script setup lang="ts">
import { PhLockKey, PhShieldCheck } from "@phosphor-icons/vue";
import { useRouter } from "vue-router";

import AgentWorkflow from "../components/AgentWorkflow.vue";
import OperationalNotice from "../components/OperationalNotice.vue";
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
    <section class="hero-centered" aria-labelledby="hero-title">
      <p class="hero-eyebrow">Trusted research workspace</p>
      <h1 id="hero-title" class="hero-centered-title">
        A <em>research</em> workspace for answers that hold up.
      </h1>
      <span class="hero-rule hero-rule-centered" aria-hidden="true"></span>
      <p class="hero-copy hero-copy-centered">
        Plan the work. Inspect the evidence. Share a report with every source attached.
      </p>

      <div class="composer-centered-wrap">
        <OperationalNotice
          v-if="researchStore.operationalIssue"
          :issue="researchStore.operationalIssue"
          @action="researchStore.retryOperationalIssue(undefined)"
          @dismiss="researchStore.operationalIssue = null"
        />

        <ResearchComposer
          v-model:query="researchStore.query"
          v-model:provider="researchStore.provider"
          v-model:selected-document-ids="researchStore.selectedDocumentIds"
          :enabled-providers="enabledProviders"
          :submitting="researchStore.submitting"
          @submit="submitResearch"
        />
      </div>

      <ul class="trust-list" aria-label="Research guarantees">
        <li><PhShieldCheck :size="18" /> Sources remain inspectable</li>
        <li>
          <PhLockKey :size="18" /> Your data stays tenant-scoped and is never used for training.
        </li>
      </ul>
    </section>

    <AgentWorkflow status="idle" />

    <RecentResearchList :runs="researchStore.recentRuns" @select="selectRun" />
  </main>
</template>
