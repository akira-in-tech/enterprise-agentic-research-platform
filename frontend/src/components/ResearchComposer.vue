<script setup lang="ts">
import { PhArrowRight, PhClock, PhInfo, PhLockKey, PhSpinnerGap } from "@phosphor-icons/vue";
import { computed } from "vue";

import type { UserFacingProvider } from "../types/research";
import ProviderMenu from "./ProviderMenu.vue";

const props = defineProps<{
  query: string;
  provider: UserFacingProvider;
  enabledProviders?: readonly UserFacingProvider[];
  submitting: boolean;
}>();

const emit = defineEmits<{
  "update:query": [query: string];
  "update:provider": [provider: UserFacingProvider];
  submit: [];
}>();

const queryLength = computed(() => props.query.trim().length);
const canSubmit = computed(() => queryLength.value > 0 && !props.submitting);

function handleKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && canSubmit.value) {
    event.preventDefault();
    emit("submit");
  }
}
</script>

<template>
  <form class="research-composer" aria-label="Start new research" @submit.prevent="emit('submit')">
    <label class="sr-only" for="research-question">Research question</label>
    <textarea
      id="research-question"
      :value="query"
      rows="3"
      maxlength="4000"
      placeholder="What would you like to understand?"
      @input="emit('update:query', ($event.target as HTMLTextAreaElement).value)"
      @keydown="handleKeydown"
    />

    <div class="composer-toolbar">
      <div class="composer-options">
        <ProviderMenu
          :model-value="provider"
          :enabled-providers="enabledProviders"
          :disabled="submitting"
          @update:model-value="emit('update:provider', $event)"
        />
        <span class="toolbar-divider" aria-hidden="true"></span>
        <button
          class="knowledge-button"
          type="button"
          disabled
          aria-label="Private knowledge, coming soon"
          aria-describedby="knowledge-help"
        >
          <PhLockKey :size="16" />
          <span>Private knowledge</span>
          <span class="preview-badge">Soon</span>
        </button>
        <span id="knowledge-help" class="sr-only">
          Private knowledge selection is not yet exposed by the public research endpoint.
        </span>
      </div>

      <button class="submit-button" type="submit" :disabled="!canSubmit">
        <PhSpinnerGap v-if="submitting" class="spin" :size="17" weight="bold" />
        <template v-else>
          <span>Start research</span>
          <PhArrowRight :size="16" weight="bold" />
        </template>
      </button>
    </div>

    <div class="composer-footnote">
      <span><PhClock :size="14" /> Durable background job · Safe to leave this page</span>
      <span class="shortcut-hint"><PhInfo :size="14" /> {{ queryLength }}/4000 · ⌘ Enter</span>
    </div>
  </form>
</template>
