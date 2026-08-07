<script setup lang="ts">
import { PhSignOut, PhUserCircle } from "@phosphor-icons/vue";
import { nextTick, ref } from "vue";

defineProps<{
  userDisplayName: string | null;
  userEmail: string;
  tenantName: string;
  initials: string;
}>();

const emit = defineEmits<{
  editProfile: [];
  logout: [];
}>();

const open = ref(false);
const trigger = ref<HTMLButtonElement | null>(null);
const menu = ref<HTMLDivElement | null>(null);

function toggle(): void {
  open.value = !open.value;
}

function close(): void {
  open.value = false;
}

function editProfile(): void {
  close();
  emit("editProfile");
}

function logout(): void {
  close();
  emit("logout");
}

function onTriggerKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    open.value = true;
    void nextTick(() => menu.value?.querySelector<HTMLButtonElement>("button")?.focus());
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
  <div class="provider-picker profile-menu">
    <button
      ref="trigger"
      class="avatar-button"
      type="button"
      aria-haspopup="menu"
      :aria-expanded="open"
      aria-label="Account menu"
      title="Account"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      {{ initials }}
    </button>

    <Transition name="popover">
      <div
        v-if="open"
        ref="menu"
        class="provider-popover profile-popover"
        role="menu"
        aria-label="Account menu"
        @keydown="onMenuKeydown"
      >
        <div class="profile-identity">
          <span class="avatar-button" aria-hidden="true">{{ initials }}</span>
          <span class="profile-copy">
            <strong>{{ userDisplayName ?? userEmail }}</strong>
            <small>{{ userEmail }}</small>
            <small>{{ tenantName }}</small>
          </span>
        </div>
        <button class="provider-option" type="button" role="menuitem" @click="editProfile">
          <span class="provider-icon provider-icon-local"><PhUserCircle :size="19" /></span>
          <span class="provider-copy">
            <strong>Edit profile</strong>
            <small>Display name and password</small>
          </span>
        </button>
        <button class="provider-option" type="button" role="menuitem" @click="logout">
          <span class="provider-icon provider-icon-danger"><PhSignOut :size="19" /></span>
          <span class="provider-copy">
            <strong>Log out</strong>
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>
