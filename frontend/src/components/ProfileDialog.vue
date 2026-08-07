<script setup lang="ts">
import { PhX } from "@phosphor-icons/vue";
import { ref } from "vue";

import { useAuthStore } from "../stores/auth";

const emit = defineEmits<{
  close: [];
}>();

const authStore = useAuthStore();

const displayName = ref(authStore.user?.display_name ?? "");
const nameSubmitting = ref(false);
const nameError = ref("");
const nameSuccess = ref(false);

const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const passwordSubmitting = ref(false);
const passwordError = ref("");
const passwordSuccess = ref(false);

async function saveDisplayName(): Promise<void> {
  nameSubmitting.value = true;
  nameError.value = "";
  nameSuccess.value = false;

  try {
    const success = await authStore.updateDisplayName(displayName.value);

    if (success) {
      nameSuccess.value = true;
    } else {
      nameError.value = authStore.error;
    }
  } finally {
    nameSubmitting.value = false;
  }
}

async function savePassword(): Promise<void> {
  passwordError.value = "";
  passwordSuccess.value = false;

  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = "New password and confirmation do not match.";
    return;
  }

  passwordSubmitting.value = true;

  try {
    const success = await authStore.changePassword({
      currentPassword: currentPassword.value,
      newPassword: newPassword.value,
    });

    if (success) {
      passwordSuccess.value = true;
      currentPassword.value = "";
      newPassword.value = "";
      confirmPassword.value = "";
    } else {
      passwordError.value = authStore.error;
    }
  } finally {
    passwordSubmitting.value = false;
  }
}

function close(): void {
  emit("close");
}

function onBackdropClick(event: MouseEvent): void {
  if (event.target === event.currentTarget) close();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") close();
}
</script>

<template>
  <div class="dialog-backdrop" @click="onBackdropClick" @keydown="onKeydown">
    <div
      class="workspace-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-dialog-title"
    >
      <button class="dialog-close" type="button" aria-label="Close" @click="close">
        <PhX :size="18" />
      </button>
      <p class="eyebrow">Account</p>
      <h1 id="profile-dialog-title">Edit profile</h1>
      <p class="dialog-intro">
        Update how your name appears across Evident, or change your password.
      </p>

      <form class="auth-form" @submit.prevent="saveDisplayName">
        <label>
          <span>Display name</span>
          <input v-model="displayName" type="text" autocomplete="name" placeholder="Your name" />
        </label>
        <p v-if="nameError" class="field-error" role="alert">{{ nameError }}</p>
        <p v-if="nameSuccess" class="field-success">Display name updated.</p>
        <div class="dialog-actions">
          <button class="primary-button" type="submit" :disabled="nameSubmitting">
            {{ nameSubmitting ? "Saving..." : "Save name" }}
          </button>
        </div>
      </form>

      <hr class="dialog-divider" />

      <form class="auth-form" @submit.prevent="savePassword">
        <label>
          <span>Current password</span>
          <input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            required
          />
        </label>
        <label>
          <span>New password</span>
          <input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required
          />
        </label>
        <label>
          <span>Confirm new password</span>
          <input
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required
          />
        </label>
        <p v-if="passwordError" class="field-error" role="alert">{{ passwordError }}</p>
        <p v-if="passwordSuccess" class="field-success">Password changed.</p>
        <div class="dialog-actions">
          <button class="primary-button" type="submit" :disabled="passwordSubmitting">
            {{ passwordSubmitting ? "Saving..." : "Change password" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
