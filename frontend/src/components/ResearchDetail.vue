<script setup lang="ts">
import {
  PhArrowLeft,
  PhArrowSquareOut,
  PhCaretDown,
  PhCheckCircle,
  PhCircleNotch,
  PhFileText,
  PhGlobe,
  PhLockKey,
  PhPlugs,
  PhWarningCircle,
} from "@phosphor-icons/vue";
import { computed, ref, watch } from "vue";

import type {
  OperationalIssue,
  RecentResearchRun,
  ResearchAgentId,
  ResearchProgressRecord,
  ResearchReport,
  ResearchReportSource,
} from "../types/research";
import AgentWorkflow from "./AgentWorkflow.vue";
import OperationalNotice from "./OperationalNotice.vue";

const props = defineProps<{
  run: RecentResearchRun;
  progress: ResearchProgressRecord | null;
  report: ResearchReport | null;
  loadingReport: boolean;
  operationalIssue: OperationalIssue | null;
}>();

const emit = defineEmits<{
  back: [];
  retry: [];
  retryIssue: [];
  dismissIssue: [];
}>();

const evidenceOpen = ref(false);

watch(
  () => props.run.id,
  () => {
    evidenceOpen.value = false;
  },
);

const displayStatus = computed(() => props.progress?.status ?? props.run.status);
const displayMessage = computed(() => props.progress?.message ?? props.run.message);
const citationCoverage = computed(() => Math.round((props.report?.citation_coverage ?? 0) * 100));
const citedSources = computed(() => props.report?.sources.filter((source) => source.cited).length ?? 0);
const reportApproved = computed(
  () => props.report?.citation_valid === true && props.report.reflection_status === "approved",
);

const activeAgent = computed<ResearchAgentId>(() => {
  const state = props.progress?.workflow_status?.toLowerCase() ?? "";
  if (state.includes("scope") || state.includes("classif")) return "scope";
  if (state.includes("plan")) return "plan";
  if (state.includes("retriev") || state.includes("search")) return "retrieve";
  if (state.includes("private") || state.includes("rag")) return "private_rag";
  if (state.includes("verif") || state.includes("reflect")) return "verify";
  if (state.includes("synth")) return "synthesize";
  if (state.includes("report") || state.includes("write")) return "report";
  return "analyze";
});

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

    <OperationalNotice
      v-if="operationalIssue"
      class="detail-notice"
      :issue="operationalIssue"
      @action="emit('retryIssue')"
      @dismiss="emit('dismissIssue')"
    />

    <template v-if="displayStatus !== 'completed'">
      <section class="progress-card" aria-live="polite">
        <span class="progress-icon" :class="`status-${displayStatus}`">
          <PhWarningCircle v-if="displayStatus === 'failed'" :size="24" weight="fill" />
          <PhCircleNotch v-else class="spin" :size="24" />
        </span>
        <div>
          <p class="status-kicker">{{ displayStatus === "failed" ? "Research stopped" : "Research in progress" }}</p>
          <h2>{{ displayMessage }}</h2>
          <p v-if="progress?.workflow_status" class="workflow-state">Current state: {{ progress.workflow_status }}</p>
          <p v-if="progress?.error_message" class="error-detail">{{ progress.error_message }}</p>
        </div>
        <button v-if="displayStatus === 'failed'" class="secondary-button" type="button" @click="emit('retry')">
          Try again
        </button>
      </section>
      <AgentWorkflow :active-agent="activeAgent" compact />
    </template>

    <section v-else-if="loadingReport" class="report-loading" aria-live="polite">
      <PhCircleNotch class="spin" :size="22" /> Loading the durable report…
    </section>

    <template v-else-if="report">
      <article class="report-document">
        <div class="report-heading-row">
          <div>
            <p class="eyebrow">Answer</p>
            <h2>Research conclusion</h2>
          </div>
          <span class="approved-badge" :class="{ 'revision-badge': !reportApproved }">
            <PhCheckCircle v-if="reportApproved" :size="16" weight="fill" />
            <PhWarningCircle v-else :size="16" weight="fill" />
            {{ reportApproved ? "Verified" : "Revision required" }}
          </span>
        </div>
        <div class="report-content">{{ report.content }}</div>
      </article>

      <section class="quality-panel" aria-labelledby="quality-heading">
        <div>
          <p class="eyebrow">Research quality</p>
          <h2 id="quality-heading">Why this answer holds up</h2>
        </div>
        <dl class="quality-metrics">
          <div>
            <dt>Citation coverage</dt>
            <dd>{{ citationCoverage }}%</dd>
          </div>
          <div>
            <dt>Cited sources</dt>
            <dd>{{ citedSources }} / {{ report.sources.length }}</dd>
          </div>
          <div>
            <dt>Verification</dt>
            <dd>{{ reportApproved ? "Passed" : "Needs review" }}</dd>
          </div>
        </dl>
        <button
          class="evidence-toggle"
          type="button"
          :aria-expanded="evidenceOpen"
          aria-controls="evidence-panel"
          @click="evidenceOpen = !evidenceOpen"
        >
          <span>
            <strong>{{ evidenceOpen ? "Hide evidence" : "Inspect evidence" }}</strong>
            <small>Sources stay collapsed to protect report reading width.</small>
          </span>
          <PhCaretDown :size="18" :class="{ 'caret-open': evidenceOpen }" />
        </button>
      </section>

      <Transition name="evidence">
        <aside v-if="evidenceOpen" id="evidence-panel" class="evidence-panel" aria-labelledby="evidence-heading">
          <div class="evidence-heading-row">
            <div>
              <p class="eyebrow">Traceability</p>
              <h2 id="evidence-heading">Evidence</h2>
            </div>
            <span>{{ citedSources }} cited</span>
          </div>
          <div class="source-list">
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
          </div>
          <div v-if="report.sources.length === 0" class="empty-evidence">
            <PhFileText :size="20" /> No source records were attached to this report.
          </div>
        </aside>
      </Transition>
    </template>
  </main>
</template>
