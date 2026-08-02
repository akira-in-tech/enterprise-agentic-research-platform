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
} from "@phosphor-icons/vue";
import { computed } from "vue";

import type { ResearchAgentId } from "../types/research";

const props = withDefaults(
  defineProps<{
    activeAgent?: ResearchAgentId;
    completed?: boolean;
    compact?: boolean;
  }>(),
  {
    activeAgent: "analyze",
    completed: false,
    compact: false,
  },
);

const agents = [
  { id: "scope", label: "Scope", icon: PhSlidersHorizontal },
  { id: "plan", label: "Plan", icon: PhListChecks },
  { id: "retrieve", label: "Retrieve", icon: PhMagnifyingGlass },
  { id: "private_rag", label: "Private RAG", icon: PhLockKey },
  { id: "analyze", label: "Analyze", icon: PhChartLineUp },
  { id: "verify", label: "Verify", icon: PhShieldCheck },
  { id: "synthesize", label: "Synthesize", icon: PhSparkle },
  { id: "report", label: "Report", icon: PhFileText },
] as const;

const activeIndex = computed(() =>
  props.completed ? agents.length : Math.max(0, agents.findIndex((agent) => agent.id === props.activeAgent)),
);

function stateFor(index: number): "complete" | "active" | "pending" {
  if (props.completed || index < activeIndex.value) return "complete";
  if (index === activeIndex.value) return "active";
  return "pending";
}
</script>

<template>
  <section class="agent-workflow" :class="{ 'agent-workflow-compact': compact }" aria-labelledby="agent-flow-title">
    <div class="agent-workflow-heading">
      <div>
        <span class="live-dot" aria-hidden="true"></span>
        <h2 id="agent-flow-title">8-agent research flow</h2>
      </div>
      <p>{{ completed ? "Completed with a traceable report" : "Agents share one evidence trail" }}</p>
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
          <component :is="agent.icon" v-else :size="18" />
        </span>
        <span class="agent-label">
          <strong>{{ agent.label }}</strong>
          <small v-if="stateFor(index) === 'active'">Working</small>
        </span>
      </li>
    </ol>
  </section>
</template>
