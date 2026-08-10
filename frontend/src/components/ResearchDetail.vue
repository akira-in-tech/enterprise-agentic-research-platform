<script setup lang="ts">
import {
  PhArrowLeft,
  PhArrowSquareOut,
  PhCaretDown,
  PhCheckCircle,
  PhCircleNotch,
  PhFileText,
  PhGlobe,
  PhGraduationCap,
  PhLockKey,
  PhPlugs,
  PhWarningCircle,
} from "@phosphor-icons/vue";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed, nextTick, ref, watch } from "vue";

import { downloadResearchReport, ResearchApiError } from "../lib/research-api";
import type {
  OperationalIssue,
  RecentResearchRun,
  ReportCitationStyle,
  ReportExportFormat,
  ResearchAgentId,
  ResearchProgressRecord,
  ResearchReport,
  ResearchReportSource,
} from "../types/research";
import AgentWorkflow from "./AgentWorkflow.vue";
import DownloadOptionsMenu from "./DownloadOptionsMenu.vue";
import OperationalNotice from "./OperationalNotice.vue";

const CITATION_PATTERN = /\[(WEB|PRIVATE|MCP|PAPER)-([0-9A-F]{16})\]/g;

const props = defineProps<{
  run: RecentResearchRun;
  progress: ResearchProgressRecord | null;
  report: ResearchReport | null;
  loadingReport: boolean;
  operationalIssue: OperationalIssue | null;
}>();

const emit = defineEmits<{
  back: [];
  cancel: [];
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
const citedSources = computed(
  () => props.report?.sources.filter((source) => source.cited).length ?? 0,
);
const reportApproved = computed(
  () => props.report?.citation_valid === true && props.report.reflection_status === "approved",
);

const activeAgent = computed<ResearchAgentId>(() => {
  const state = props.progress?.workflow_status?.toLowerCase() ?? "";
  if (state.includes("intent") || state.includes("rout") || state.includes("classif"))
    return "intent_router";
  if (state.includes("plan")) return "planner";
  if (state.includes("private") || state.includes("local") || state.includes("rag"))
    return "local_scout";
  if (state.includes("web") || state.includes("retriev") || state.includes("search"))
    return "web_scout";
  if (state.includes("evidence") || state.includes("judg") || state.includes("verif"))
    return "evidence_judge";
  if (state.includes("reflect") || state.includes("revision")) return "reflect";
  if (state.includes("report") || state.includes("writ")) return "writer";
  return "analyst";
});

function sourceIcon(source: ResearchReportSource): typeof PhGlobe {
  if (source.source_type === "paper") return PhGraduationCap;
  if (source.origin === "private") return PhLockKey;
  if (source.origin === "mcp") return PhPlugs;
  return PhGlobe;
}

function sourceScore(source: ResearchReportSource): string {
  return `${Math.round(source.overall_score * 100)}%`;
}

const sourceIndexById = computed(() => {
  const index = new Map<string, number>();
  for (const [position, source] of (props.report?.sources ?? []).entries()) {
    index.set(source.source_id, position + 1);
  }
  return index;
});

const renderedReportHtml = computed(() => {
  if (!props.report) return "";

  const withCitationLinks = props.report.content.replace(CITATION_PATTERN, (match, origin, hex) => {
    const sourceId = `${origin}-${hex}`;
    const displayNumber = sourceIndexById.value.get(sourceId);

    if (displayNumber === undefined) return match;

    return `<sup class="citation-link"><a href="#source-${sourceId}" data-source-id="${sourceId}">${displayNumber}</a></sup>`;
  });

  return DOMPurify.sanitize(marked.parse(withCitationLinks, { async: false }) as string);
});

const highlightedSourceId = ref<string | null>(null);
let highlightTimeout: ReturnType<typeof setTimeout> | undefined;

function focusSource(sourceId: string): void {
  evidenceOpen.value = true;
  highlightedSourceId.value = sourceId;
  clearTimeout(highlightTimeout);
  highlightTimeout = setTimeout(() => {
    highlightedSourceId.value = null;
  }, 2000);

  void nextTick(() => {
    document
      .getElementById(`source-${sourceId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

function handleReportContentClick(event: MouseEvent): void {
  const link = (event.target as HTMLElement).closest<HTMLElement>("a[data-source-id]");
  const sourceId = link?.dataset.sourceId;

  if (!sourceId) return;

  event.preventDefault();
  focusSource(sourceId);
}

const downloading = ref(false);
const downloadError = ref("");

async function downloadReport(
  format: ReportExportFormat,
  citationStyle: ReportCitationStyle,
): Promise<void> {
  if (downloading.value) return;

  downloading.value = true;
  downloadError.value = "";

  try {
    const blob = await downloadResearchReport(props.run.id, format, citationStyle);
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    const extension = format === "pdf" ? "pdf" : "md";
    link.download = `report-${props.run.id}-${citationStyle}.${extension}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (error) {
    downloadError.value =
      error instanceof ResearchApiError ? error.message : "The report could not be downloaded.";
  } finally {
    downloading.value = false;
  }
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
      <span class="detail-provider">{{
        run.provider === "qwen" ? "Qwen Local" : "Claude Cloud"
      }}</span>
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
          <PhWarningCircle
            v-if="displayStatus === 'failed' || displayStatus === 'cancelled'"
            :size="24"
            weight="fill"
          />
          <PhCircleNotch v-else class="spin" :size="24" />
        </span>
        <div>
          <p class="status-kicker">
            {{
              displayStatus === "failed"
                ? "Research stopped"
                : displayStatus === "cancelled"
                  ? "Research cancelled"
                  : "Research in progress"
            }}
          </p>
          <h2>{{ displayMessage }}</h2>
          <p v-if="progress?.workflow_status" class="workflow-state">
            Current state: {{ progress.workflow_status }}
          </p>
          <p v-if="progress?.error_message" class="error-detail">{{ progress.error_message }}</p>
        </div>
        <button
          v-if="displayStatus === 'failed'"
          class="secondary-button"
          type="button"
          @click="emit('retry')"
        >
          Try again
        </button>
        <button
          v-else-if="displayStatus === 'queued' || displayStatus === 'running'"
          class="secondary-button"
          type="button"
          @click="emit('cancel')"
        >
          Cancel research
        </button>
      </section>
      <AgentWorkflow :active-agent="activeAgent" :status="displayStatus" compact />
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
          <div class="report-heading-actions">
            <span class="approved-badge" :class="{ 'revision-badge': !reportApproved }">
              <PhCheckCircle v-if="reportApproved" :size="16" weight="fill" />
              <PhWarningCircle v-else :size="16" weight="fill" />
              {{ reportApproved ? "Verified" : "Revision required" }}
            </span>
            <DownloadOptionsMenu :downloading="downloading" @download="downloadReport" />
          </div>
        </div>
        <p v-if="downloadError" class="field-error" role="alert">{{ downloadError }}</p>
        <div v-if="report.human_review_required" class="human-review-notice" role="alert">
          <PhWarningCircle :size="20" aria-hidden="true" />
          <div>
            <strong>Human review required</strong>
            <p>
              {{
                report.human_review_reason ??
                "This request touches a high-risk domain (medical, legal, financial, or safety-critical). Evidence and citations below do not substitute for a qualified human reviewer."
              }}
            </p>
          </div>
        </div>
        <!-- eslint-disable vue/no-v-html -- renderedReportHtml is DOMPurify-sanitized above -->
        <div
          class="report-content"
          @click="handleReportContentClick"
          v-html="renderedReportHtml"
        ></div>
        <!-- eslint-enable vue/no-v-html -->
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
        <aside
          v-if="evidenceOpen"
          id="evidence-panel"
          class="evidence-panel"
          aria-labelledby="evidence-heading"
        >
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
              :id="`source-${source.source_id}`"
              :key="source.source_id"
              class="source-card"
              :class="{ 'source-card-highlighted': source.source_id === highlightedSourceId }"
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
