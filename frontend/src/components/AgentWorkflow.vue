<script setup lang="ts">
import {
  PhChartLineUp,
  PhCheck,
  PhFileText,
  PhListChecks,
  PhLockKey,
  PhMagnifyingGlass,
  PhShieldCheck,
  PhSlidersHorizontal,
  PhSparkle,
  PhWarningCircle,
} from "@phosphor-icons/vue";
import { computed } from "vue";

import type { ProgressStatus, ResearchAgentId } from "../types/research";

const props = withDefaults(
  defineProps<{
    activeAgent?: ResearchAgentId;
    status?: ProgressStatus | "idle";
    compact?: boolean;
  }>(),
  {
    activeAgent: undefined,
    status: "idle",
    compact: false,
  },
);

const agents = [
  { id: "intent_router", label: "Intent Router", icon: PhSlidersHorizontal },
  { id: "planner", label: "Planner", icon: PhListChecks },
  { id: "web_scout", label: "Web Scout", icon: PhMagnifyingGlass },
  { id: "local_scout", label: "Local Scout", icon: PhLockKey },
  { id: "evidence_judge", label: "Evidence Judge", icon: PhShieldCheck },
  { id: "analyst", label: "Analyst", icon: PhChartLineUp },
  { id: "reflect", label: "Reflect", icon: PhSparkle },
  { id: "writer", label: "Writer", icon: PhFileText },
] as const;

const isStopped = computed(() => props.status === "failed" || props.status === "cancelled");

const activeIndex = computed(() => {
  if (props.status === "completed") return agents.length;
  if (props.status === "idle" || props.activeAgent === undefined) return -1;

  return Math.max(
    0,
    agents.findIndex((agent) => agent.id === props.activeAgent),
  );
});

function stateFor(index: number): "complete" | "active" | "failed" | "pending" {
  if (props.status === "completed") return "complete";
  if (activeIndex.value === -1) return "pending";
  if (index < activeIndex.value) return "complete";
  if (index === activeIndex.value) return isStopped.value ? "failed" : "active";
  return "pending";
}

const subtitle = computed(() => {
  if (props.status === "completed") return "Completed with a traceable report";
  if (isStopped.value) return "Research workflow stopped before completing";
  return "Agents share one evidence trail";
});
</script>

<template>
  <section
    class="agent-workflow"
    :class="{ 'agent-workflow-compact': compact }"
    aria-labelledby="agent-flow-title"
  >
    <div class="agent-workflow-heading">
      <div>
        <span class="live-dot" aria-hidden="true"></span>
        <h2 id="agent-flow-title">8-agent research flow</h2>
      </div>
      <p>{{ subtitle }}</p>
    </div>

    <ol class="agent-track" aria-label="Research agents">
      <li
        v-for="(agent, index) in agents"
        :key="agent.id"
        class="agent-step"
        :class="`agent-${stateFor(index)}`"
        :aria-current="stateFor(index) === 'active' ? 'step' : undefined"
      >
        <span class="agent-icon" aria-hidden="true">
          <PhCheck v-if="stateFor(index) === 'complete'" :size="14" weight="bold" />
          <PhWarningCircle v-else-if="stateFor(index) === 'failed'" :size="18" weight="bold" />
          <component :is="agent.icon" v-else :size="18" />
        </span>
        <span class="agent-label">
          <strong>{{ agent.label }}</strong>
          <small v-if="stateFor(index) === 'active'">Working</small>
          <small v-else-if="stateFor(index) === 'failed'">Needs attention</small>
        </span>
      </li>
    </ol>
  </section>
</template>
