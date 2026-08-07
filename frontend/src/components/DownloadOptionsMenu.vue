<script setup lang="ts">
import {
  PhCaretDown,
  PhCircleNotch,
  PhDownloadSimple,
  PhFileMd,
  PhFilePdf,
} from "@phosphor-icons/vue";
import { nextTick, ref } from "vue";

import type { ReportCitationStyle, ReportExportFormat } from "../types/research";

defineProps<{
  downloading?: boolean;
}>();

const emit = defineEmits<{
  download: [format: ReportExportFormat, citationStyle: ReportCitationStyle];
}>();

interface DownloadOption {
  format: ReportExportFormat;
  citationStyle: ReportCitationStyle;
  label: string;
  detail: string;
}

const options: DownloadOption[] = [
  {
    format: "markdown",
    citationStyle: "numbered",
    label: "Markdown · Numbered",
    detail: "[1][2] citations with a References list",
  },
  {
    format: "markdown",
    citationStyle: "footnote",
    label: "Markdown · Footnote",
    detail: "Superscript citations with a Notes list",
  },
  {
    format: "pdf",
    citationStyle: "numbered",
    label: "PDF · Numbered",
    detail: "[1][2] citations with a References list",
  },
  {
    format: "pdf",
    citationStyle: "footnote",
    label: "PDF · Footnote",
    detail: "Superscript citations with a Notes list",
  },
];

const open = ref(false);
const trigger = ref<HTMLButtonElement | null>(null);
const menu = ref<HTMLDivElement | null>(null);

function toggle(): void {
  open.value = !open.value;
}

function select(option: DownloadOption): void {
  emit("download", option.format, option.citationStyle);
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
  const items = Array.from(menu.value?.querySelectorAll<HTMLButtonElement>("[role=option]") ?? []);
  const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);

  if (event.key === "Escape") {
    event.preventDefault();
    open.value = false;
    trigger.value?.focus();
  } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const direction = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = (currentIndex + direction + items.length) % items.length;
    items[nextIndex]?.focus();
  }
}
</script>

<template>
  <div class="download-picker">
    <button
      ref="trigger"
      class="secondary-button download-button"
      type="button"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :disabled="downloading"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <PhCircleNotch v-if="downloading" class="spin" :size="15" />
      <PhDownloadSimple v-else :size="15" />
      {{ downloading ? "Preparing…" : "Download" }}
      <PhCaretDown :size="13" :class="{ 'caret-open': open }" />
    </button>

    <Transition name="popover">
      <div
        v-if="open"
        ref="menu"
        class="provider-popover download-popover"
        role="listbox"
        aria-label="Download format and citation style"
        @keydown="onMenuKeydown"
      >
        <div class="popover-heading">
          <span>Download report</span>
        </div>
        <button
          v-for="option in options"
          :key="`${option.format}-${option.citationStyle}`"
          class="provider-option"
          type="button"
          role="option"
          :aria-selected="false"
          @click="select(option)"
        >
          <span class="provider-icon provider-icon-local">
            <PhFilePdf v-if="option.format === 'pdf'" :size="19" weight="duotone" />
            <PhFileMd v-else :size="19" weight="duotone" />
          </span>
          <span class="provider-copy">
            <strong>{{ option.label }}</strong>
            <small>{{ option.detail }}</small>
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>
