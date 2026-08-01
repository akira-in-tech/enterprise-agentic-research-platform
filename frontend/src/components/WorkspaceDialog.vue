<script setup lang="ts">
import { PhCheck, PhX } from "@phosphor-icons/vue";
import { computed, ref, watch } from "vue";

import type { WorkspaceContext } from "../types/research";

const props = defineProps<{
  open: boolean;
  workspace: WorkspaceContext;
}>();

const emit = defineEmits<{
  close: [];
  save: [workspace: WorkspaceContext];
}>();

const tenantId = ref("");
const userId = ref("");
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

watch(
  () => props.open,
  (open) => {
    if (open) {
      tenantId.value = props.workspace.tenantId;
      userId.value = props.workspace.userId;
    }
  },
  { immediate: true },
);

const valid = computed(
  () => uuidPattern.test(tenantId.value.trim()) && (!userId.value.trim() || uuidPattern.test(userId.value.trim())),
);

function save(): void {
  if (!valid.value) return;
  emit("save", { tenantId: tenantId.value.trim(), userId: userId.value.trim() });
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="dialog-backdrop" @mousedown.self="emit('close')">
        <section
          class="workspace-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="workspace-title"
        >
          <button class="dialog-close" type="button" aria-label="Close workspace settings" @click="emit('close')">
            <PhX :size="18" />
          </button>
          <p class="eyebrow">Developer context</p>
          <h2 id="workspace-title">Connect a workspace</h2>
          <p class="dialog-intro">
            Requests are tenant-scoped by the API. These identifiers stay in this browser and are sent as headers.
          </p>
          <label>
            <span>Tenant ID <strong aria-hidden="true">*</strong></span>
            <input v-model="tenantId" type="text" autocomplete="off" placeholder="UUID" />
          </label>
          <label>
            <span>User ID <small>optional</small></span>
            <input v-model="userId" type="text" autocomplete="off" placeholder="UUID" />
          </label>
          <p v-if="tenantId && !valid" class="field-error" role="alert">Use valid UUID values.</p>
          <div class="dialog-actions">
            <button class="secondary-button" type="button" @click="emit('close')">Cancel</button>
            <button class="primary-button" type="button" :disabled="!valid" @click="save">
              <PhCheck :size="16" weight="bold" /> Save workspace
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
