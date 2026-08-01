<script setup lang="ts">
import {
  PhArrowLeft,
  PhArrowSquareOut,
  PhCheckCircle,
  PhCircleNotch,
  PhFileText,
  PhGlobe,
  PhLockKey,
  PhPlugs,
  PhWarningCircle,
} from "@phosphor-icons/vue";
import { computed } from "vue";

import type {
  RecentResearchRun,
  ResearchProgressRecord,
  ResearchReport,
  ResearchReportSource,
} from "../types/research";

const props = defineProps<{
  run: RecentResearchRun;
  progress: ResearchProgressRecord | null;
  report: ResearchReport | null;
  loadingReport: boolean;
}>();

const emit = defineEmits<{
  back: [];
  retry: [];
}>();

const displayStatus = computed(() => props.progress?.status ?? props.run.status);
const displayMessage = computed(() => props.progress?.message ?? props.run.message);

function sourceIcon(source: ResearchReportSource): typeof PhGlobe {
  if (source.origin === "private") return PhLockKey;
  if (source.origin === "mcp") return PhPlugs;
  return PhGlobe;
}

function sourceScore(source: ResearchReportSource): string {
  return `${Math.round(source.overall_score * 100)}%`;
}
</script>

<template>
  <main id="main" class="detail-page" tabindex="-1">
    <button class="back-button" type="button" @click="emit('back')">
      <PhArrowLeft :size="17" /> Back to research
    </button>

    <header class="detail-header">
      <div>
        <p class="eyebrow">Research run</p>
        <h1>{{ run.query }}</h1>
      </div>
      <span class="detail-provider">{{ run.provider === "qwen" ? "Qwen Local" : "Claude Cloud" }}</span>
    </header>

    <section v-if="displayStatus !== 'completed'" class="progress-card" aria-live="polite">
      <span class="progress-icon" :class="`status-${displayStatus}`">
        <PhWarningCircle v-if="displayStatus === 'failed'" :size="24" weight="fill" />
        <PhCircleNotch v-else class="spin" :size="24" />
      </span>
      <div>
        <p class="status-kicker">{{ displayStatus === "failed" ? "Research stopped" : "Research in progress" }}</p>
        <h2>{{ displayMessage }}</h2>
        <p v-if="progress?.workflow_status" class="workflow-state">Workflow state: {{ progress.workflow_status }}</p>
        <p v-if="progress?.error_message" class="error-detail">{{ progress.error_message }}</p>
      </div>
      <button v-if="displayStatus === 'failed'" class="secondary-button" type="button" @click="emit('retry')">
        Try again
      </button>
    </section>

    <section v-else-if="loadingReport" class="report-loading" aria-live="polite">
      <PhCircleNotch class="spin" :size="22" /> Loading the durable report…
    </section>

    <div v-else-if="report" class="report-layout">
      <article class="report-document">
        <div class="report-status-row">
          <span class="approved-badge"><PhCheckCircle :size="16" weight="fill" /> Approved</span>
          <span>{{ Math.round(report.citation_coverage * 100) }}% citation coverage</span>
          <span>{{ report.sources.length }} sources</span>
        </div>
        <div class="report-content">{{ report.content }}</div>
      </article>

      <aside class="evidence-panel" aria-labelledby="evidence-heading">
        <div class="evidence-heading-row">
          <div>
            <p class="eyebrow">Traceability</p>
            <h2 id="evidence-heading">Evidence</h2>
          </div>
          <span>{{ report.sources.filter((source) => source.cited).length }} cited</span>
        </div>
        <a
          v-for="source in report.sources"
          :key="source.source_id"
          class="source-card"
          :href="source.locator"
          target="_blank"
          rel="noreferrer"
        >
          <component :is="sourceIcon(source)" :size="18" />
          <span class="source-copy">
            <strong>{{ source.title }}</strong>
            <small>{{ source.source_id }} · {{ source.provider }}</small>
          </span>
          <span class="source-score">{{ sourceScore(source) }}</span>
          <PhArrowSquareOut :size="15" />
        </a>
        <div v-if="report.sources.length === 0" class="empty-evidence">
          <PhFileText :size="20" /> No source records were attached to this report.
        </div>
      </aside>
    </div>
  </main>
</template>
