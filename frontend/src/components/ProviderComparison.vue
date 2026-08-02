<script setup lang="ts">
import { PhCheck, PhCloud, PhCpu, PhShieldCheck } from "@phosphor-icons/vue";

import type { UserFacingProvider } from "../types/research";

defineProps<{
  modelValue: UserFacingProvider;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [provider: UserFacingProvider];
}>();
</script>

<template>
  <fieldset class="provider-comparison" :disabled="disabled">
    <legend>Choose a provider</legend>
    <p class="provider-estimate-label">Per request estimate</p>

    <label class="provider-row" :class="{ selected: modelValue === 'qwen' }">
      <input
        type="radio"
        name="provider-comparison"
        value="qwen"
        :checked="modelValue === 'qwen'"
        @change="emit('update:modelValue', 'qwen')"
      />
      <span class="provider-row-icon provider-icon-local"><PhCpu :size="19" weight="duotone" /></span>
      <span class="provider-identity">
        <strong>Qwen Local</strong>
        <small>Private · no usage data leaves your environment</small>
      </span>
      <span class="provider-attribute"><PhShieldCheck :size="15" /> Maximum privacy</span>
      <span class="provider-attribute"><strong>•••••</strong> Synthesis</span>
      <span class="provider-attribute"><strong>$</strong> Low cost</span>
      <span class="provider-price">~$0.02</span>
      <span v-if="modelValue === 'qwen'" class="provider-selected-mark" aria-hidden="true">
        <PhCheck :size="13" weight="bold" />
      </span>
    </label>

    <label class="provider-row" :class="{ selected: modelValue === 'claude' }">
      <input
        type="radio"
        name="provider-comparison"
        value="claude"
        :checked="modelValue === 'claude'"
        @change="emit('update:modelValue', 'claude')"
      />
      <span class="provider-row-icon provider-icon-cloud"><PhCloud :size="19" weight="duotone" /></span>
      <span class="provider-identity">
        <strong>Claude Cloud</strong>
        <small>Stronger synthesis · usage billed</small>
      </span>
      <span class="provider-attribute"><PhShieldCheck :size="15" /> High privacy</span>
      <span class="provider-attribute"><strong>••••○</strong> Synthesis</span>
      <span class="provider-attribute"><strong>$$$</strong> Higher cost</span>
      <span class="provider-price">~$0.18</span>
      <span v-if="modelValue === 'claude'" class="provider-selected-mark" aria-hidden="true">
        <PhCheck :size="13" weight="bold" />
      </span>
    </label>

    <p class="provider-comparison-note">Estimates vary with query complexity and research depth.</p>
  </fieldset>
</template>
