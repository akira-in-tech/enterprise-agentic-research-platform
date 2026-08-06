<script setup lang="ts">
import {
  PhArrowRight,
  PhCheck,
  PhCircleNotch,
  PhFileText,
  PhWarning,
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

function statusLabel(run: RecentResearchRun): string {
  if (run.status === "completed") return "Report ready";
  if (run.status === "failed") return "Needs attention";
  if (run.status === "cancelled") return "Cancelled";
  return "In progress";
}
</script>

<template>
  <section class="recent-section" aria-labelledby="recent-heading">
    <div class="section-heading-row">
      <h2 id="recent-heading">Recent research</h2>
      <span class="local-history-label">Saved in this browser</span>
    </div>

    <div v-if="visibleRuns.length === 0" class="empty-recent">
      <span class="empty-icon" aria-hidden="true"><PhFileText :size="20" /></span>
      <div>
        <strong>No research yet</strong>
        <p>Your completed and in-progress runs will appear here.</p>
      </div>
    </div>

    <div v-else class="research-table-wrap">
      <table class="research-table">
        <caption class="sr-only">Recent research runs</caption>
        <thead>
          <tr>
            <th scope="col">Status</th>
            <th scope="col">Question</th>
            <th scope="col">Sources</th>
            <th scope="col">Citation coverage</th>
            <th scope="col">Provider</th>
            <th scope="col">Updated</th>
            <th scope="col"><span class="sr-only">Open</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in visibleRuns" :key="run.id" :class="`research-row status-${run.status}`">
            <td data-label="Status">
              <span class="table-status">
                <span class="table-status-icon" aria-hidden="true">
                  <PhCircleNotch v-if="run.status === 'queued' || run.status === 'running'" class="spin" :size="15" />
                  <PhCheck v-else-if="run.status === 'completed'" :size="14" weight="bold" />
                  <PhWarning v-else :size="15" weight="fill" />
                </span>
                {{ statusLabel(run) }}
              </span>
            </td>
            <td data-label="Question">
              <button class="research-question-button" type="button" @click="emit('select', run)">
                <strong>{{ run.query }}</strong>
                <small>{{ run.message }}</small>
              </button>
            </td>
            <td data-label="Sources">{{ run.sourceCount ?? "—" }}</td>
            <td data-label="Citation coverage">
              <span v-if="run.citationCoverage !== undefined" class="coverage-value">
                {{ Math.round(run.citationCoverage * 100) }}%
                <span class="coverage-track" aria-hidden="true">
                  <span :style="{ width: `${Math.round(run.citationCoverage * 100)}%` }"></span>
                </span>
              </span>
              <span v-else>—</span>
            </td>
            <td data-label="Provider">{{ run.provider === "qwen" ? "Qwen Local" : "Claude Cloud" }}</td>
            <td data-label="Updated">{{ relativeTime(run.updatedAt) }}</td>
            <td>
              <button class="open-run-button" type="button" :aria-label="`Open research: ${run.query}`" @click="emit('select', run)">
                <PhArrowRight :size="17" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
