<script setup lang="ts">
import {
  PhArrowRight,
  PhCheckCircle,
  PhCircleNotch,
  PhFileText,
  PhWarningCircle,
} from "@phosphor-icons/vue";
import { computed } from "vue";

import type { RecentResearchRun } from "../types/research";

const props = defineProps<{
  runs: RecentResearchRun[];
}>();

const emit = defineEmits<{
  select: [run: RecentResearchRun];
}>();

const visibleRuns = computed(() => props.runs.slice(0, 3));

function relativeTime(value: string): string {
  const elapsed = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.round(elapsed / 60_000));

  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function coverageLabel(value: number | undefined): string {
  return value === undefined ? "Report ready" : `${Math.round(value * 100)}% cited`;
}
</script>

<template>
  <section class="recent-section" aria-labelledby="recent-heading">
    <div class="section-heading-row">
      <div>
        <p class="eyebrow">Your workspace</p>
        <h2 id="recent-heading">Recent research</h2>
      </div>
      <span class="local-history-label">Saved in this browser</span>
    </div>

    <div v-if="visibleRuns.length === 0" class="empty-recent">
      <span class="empty-icon" aria-hidden="true"><PhFileText :size="20" /></span>
      <div>
        <strong>No research yet</strong>
        <p>Your completed and in-progress runs will appear here.</p>
      </div>
    </div>

    <div v-else class="run-list">
      <button
        v-for="run in visibleRuns"
        :key="run.id"
        class="run-row"
        type="button"
        @click="emit('select', run)"
      >
        <span class="run-status-icon" :class="`status-${run.status}`" aria-hidden="true">
          <PhCircleNotch v-if="run.status === 'queued' || run.status === 'running'" class="spin" :size="20" />
          <PhCheckCircle v-else-if="run.status === 'completed'" :size="20" weight="fill" />
          <PhWarningCircle v-else :size="20" weight="fill" />
        </span>
        <span class="run-main">
          <strong>{{ run.query }}</strong>
          <span class="run-meta">
            <span class="status-label" :class="`status-${run.status}`">
              {{ run.status === "running" ? "Running" : run.status.charAt(0).toUpperCase() + run.status.slice(1) }}
            </span>
            <span aria-hidden="true">·</span>
            <span v-if="run.status === 'completed'">{{ coverageLabel(run.citationCoverage) }}</span>
            <span v-else>{{ run.message }}</span>
          </span>
        </span>
        <span class="run-aside">
          <span>{{ run.provider === "qwen" ? "Qwen Local" : "Claude Cloud" }}</span>
          <span>{{ relativeTime(run.updatedAt) }}</span>
        </span>
        <PhArrowRight class="run-arrow" :size="17" />
      </button>
    </div>
  </section>
</template>
