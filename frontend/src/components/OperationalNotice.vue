<script setup lang="ts">
import {
  PhArrowsClockwise,
  PhCloudSlash,
  PhDatabase,
  PhFileX,
  PhLinkBreak,
  PhWarning,
} from "@phosphor-icons/vue";
import { computed } from "vue";

import type { OperationalIssue } from "../types/research";

const props = defineProps<{
  issue: OperationalIssue;
}>();

const emit = defineEmits<{
  action: [];
  dismiss: [];
}>();

const icon = computed(() => {
  if (props.issue.kind === "redis_unavailable") return PhDatabase;
  if (props.issue.kind === "sse_disconnected") return PhLinkBreak;
  if (props.issue.kind === "report_unavailable") return PhFileX;
  if (props.issue.kind === "citation_revision_required") return PhWarning;
  return PhCloudSlash;
});
</script>

<template>
  <section class="operational-notice" :class="`notice-${issue.kind}`" role="alert">
    <span class="notice-icon" aria-hidden="true"><component :is="icon" :size="19" /></span>
    <div>
      <strong>{{ issue.title }}</strong>
      <p>{{ issue.message }}</p>
    </div>
    <div class="notice-actions">
      <button v-if="issue.actionLabel" class="notice-action" type="button" @click="emit('action')">
        <PhArrowsClockwise :size="15" /> {{ issue.actionLabel }}
      </button>
      <button class="notice-dismiss" type="button" @click="emit('dismiss')">Dismiss</button>
    </div>
  </section>
</template>
