<script setup lang="ts">
import {
  PhCaretDown,
  PhCheck,
  PhCloud,
  PhCpu,
  PhShieldCheck,
} from "@phosphor-icons/vue";
import { computed, nextTick, ref } from "vue";

import type { UserFacingProvider } from "../types/research";

const props = withDefaults(
  defineProps<{
    modelValue: UserFacingProvider;
    enabledProviders?: readonly UserFacingProvider[];
    disabled?: boolean;
  }>(),
  {
    enabledProviders: () => ["qwen", "claude"],
  },
);

const emit = defineEmits<{
  "update:modelValue": [provider: UserFacingProvider];
}>();

const open = ref(false);
const trigger = ref<HTMLButtonElement | null>(null);
const menu = ref<HTMLDivElement | null>(null);

const selected = computed(() =>
  props.modelValue === "qwen"
    ? {
        label: "Qwen Local",
        detail: "Private · no usage cost",
      }
    : {
        label: "Claude Cloud",
        detail: "Stronger synthesis · usage billed",
      },
);

function toggle(): void {
  if (!props.disabled) {
    open.value = !open.value;
  }
}

function select(provider: UserFacingProvider): void {
  if (!props.enabledProviders.includes(provider)) {
    return;
  }

  emit("update:modelValue", provider);
  open.value = false;
  void nextTick(() => trigger.value?.focus());
}

function onTriggerKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    open.value = true;
    void nextTick(() => menu.value?.querySelector<HTMLButtonElement>("[role=option]")?.focus());
  }
}

function onMenuKeydown(event: KeyboardEvent): void {
  const options = Array.from(
    menu.value?.querySelectorAll<HTMLButtonElement>("[role=option]") ?? [],
  );
  const currentIndex = options.indexOf(document.activeElement as HTMLButtonElement);

  if (event.key === "Escape") {
    event.preventDefault();
    open.value = false;
    trigger.value?.focus();
  } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const direction = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = (currentIndex + direction + options.length) % options.length;
    options[nextIndex]?.focus();
  }
}
</script>

<template>
  <div class="provider-picker">
    <button
      ref="trigger"
      class="provider-trigger"
      type="button"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :disabled="disabled"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <PhCpu v-if="modelValue === 'qwen'" :size="17" weight="duotone" />
      <PhCloud v-else :size="17" weight="duotone" />
      <span>{{ selected.label }}</span>
      <PhCaretDown :size="13" :class="{ 'caret-open': open }" />
    </button>

    <Transition name="popover">
      <div
        v-if="open"
        ref="menu"
        class="provider-popover"
        role="listbox"
        aria-label="Language model provider"
        @keydown="onMenuKeydown"
      >
        <div class="popover-heading">
          <span>Choose a provider</span>
          <span class="popover-caption">Per request</span>
        </div>
        <button
          v-if="enabledProviders.includes('qwen')"
          class="provider-option"
          :class="{ selected: modelValue === 'qwen' }"
          type="button"
          role="option"
          :aria-selected="modelValue === 'qwen'"
          @click="select('qwen')"
        >
          <span class="provider-icon provider-icon-local"><PhCpu :size="19" weight="duotone" /></span>
          <span class="provider-copy">
            <strong>Qwen Local</strong>
            <small><PhShieldCheck :size="13" /> Private, no usage cost</small>
          </span>
          <PhCheck v-if="modelValue === 'qwen'" class="provider-check" :size="17" weight="bold" />
        </button>
        <button
          v-if="enabledProviders.includes('claude')"
          class="provider-option"
          :class="{ selected: modelValue === 'claude' }"
          type="button"
          role="option"
          :aria-selected="modelValue === 'claude'"
          @click="select('claude')"
        >
          <span class="provider-icon provider-icon-cloud"><PhCloud :size="19" weight="duotone" /></span>
          <span class="provider-copy">
            <strong>Claude Cloud</strong>
            <small>Stronger synthesis, usage billed</small>
          </span>
          <PhCheck v-if="modelValue === 'claude'" class="provider-check" :size="17" weight="bold" />
        </button>
        <p class="provider-note">The selected provider is recorded with every durable research run.</p>
      </div>
    </Transition>
  </div>
</template>
