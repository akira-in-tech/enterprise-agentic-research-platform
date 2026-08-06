<script setup lang="ts">
import { PhCaretDown, PhCheck, PhLockKey } from "@phosphor-icons/vue";
import { useQuery } from "@tanstack/vue-query";
import { computed, nextTick, ref } from "vue";

import { listKnowledgeDocuments } from "../lib/research-api";
import { useAuthStore } from "../stores/auth";
import type { KnowledgeDocument } from "../types/research";

const props = withDefaults(
  defineProps<{
    modelValue: string[];
    disabled?: boolean;
  }>(),
  {
    disabled: false,
  },
);

const emit = defineEmits<{
  "update:modelValue": [documentIds: string[]];
}>();

const authStore = useAuthStore();
const open = ref(false);
const trigger = ref<HTMLButtonElement | null>(null);
const menu = ref<HTMLDivElement | null>(null);

const { data: documents, isLoading } = useQuery({
  queryKey: computed(() => ["documents", authStore.tenant?.id]),
  queryFn: () => listKnowledgeDocuments(),
  retry: false,
  initialData: [],
});

const readyDocuments = computed(() =>
  (documents.value ?? []).filter((document: KnowledgeDocument) => document.status === "ready"),
);

function isSelected(documentId: string): boolean {
  return props.modelValue.includes(documentId);
}

function toggleDocument(documentId: string): void {
  const next = isSelected(documentId)
    ? props.modelValue.filter((id) => id !== documentId)
    : [...props.modelValue, documentId];
  emit("update:modelValue", next);
}

function searchAllDocuments(): void {
  emit("update:modelValue", []);
}

function toggle(): void {
  if (!props.disabled) {
    open.value = !open.value;
  }
}

function close(): void {
  open.value = false;
}

function onTriggerKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    open.value = true;
    void nextTick(() =>
      menu.value?.querySelector<HTMLInputElement>("input[type=checkbox]")?.focus(),
    );
  }
}

function onMenuKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault();
    close();
    trigger.value?.focus();
  }
}
</script>

<template>
  <div class="provider-picker knowledge-picker">
    <button
      ref="trigger"
      class="knowledge-button"
      type="button"
      aria-haspopup="dialog"
      :aria-expanded="open"
      :disabled="disabled"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <PhLockKey :size="16" />
      <span>Private knowledge</span>
      <span v-if="modelValue.length > 0" class="knowledge-count-badge">{{
        modelValue.length
      }}</span>
      <PhCaretDown :size="12" :class="{ 'caret-open': open }" />
    </button>

    <Transition name="popover">
      <div
        v-if="open"
        ref="menu"
        class="provider-popover knowledge-popover"
        role="dialog"
        aria-label="Scope research to private documents"
        @keydown="onMenuKeydown"
      >
        <div class="popover-heading">
          <span>Private knowledge</span>
          <span class="popover-caption">{{ readyDocuments.length }} ready</span>
        </div>

        <p v-if="isLoading" class="provider-note">Loading your documents…</p>
        <p v-else-if="readyDocuments.length === 0" class="provider-note">
          No indexed documents yet. Upload one from the Private Knowledge page, then scope research
          to it here.
        </p>
        <div v-else class="knowledge-option-list">
          <label
            v-for="document in readyDocuments"
            :key="document.id"
            class="knowledge-option"
            :class="{ selected: isSelected(document.id) }"
          >
            <input
              type="checkbox"
              :checked="isSelected(document.id)"
              @change="toggleDocument(document.id)"
            />
            <span class="knowledge-option-copy">
              <strong>{{ document.filename }}</strong>
            </span>
            <PhCheck
              v-if="isSelected(document.id)"
              class="provider-check"
              :size="15"
              weight="bold"
            />
          </label>
        </div>

        <button
          v-if="modelValue.length > 0"
          type="button"
          class="knowledge-clear"
          @click="searchAllDocuments"
        >
          Search all documents instead
        </button>

        <p class="provider-note">
          {{
            modelValue.length > 0
              ? `Research will only search ${modelValue.length} selected document${modelValue.length === 1 ? "" : "s"}.`
              : "Research searches every ready private document by default."
          }}
        </p>
      </div>
    </Transition>
  </div>
</template>
