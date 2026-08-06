<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const router = useRouter();

const email = ref("");
const password = ref("");
const tenantName = ref("");
const displayName = ref("");
const submitting = ref(false);

async function submit(): Promise<void> {
  submitting.value = true;

  try {
    const success = await authStore.register({
      email: email.value.trim(),
      password: password.value,
      tenantName: tenantName.value.trim(),
      displayName: displayName.value.trim() || undefined,
    });

    if (success) {
      await router.push("/");
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main id="main" class="auth-page" tabindex="-1">
    <section class="auth-card" aria-labelledby="register-title">
      <p class="eyebrow">Get started</p>
      <h1 id="register-title">Create your workspace</h1>
      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>Workspace name</span>
          <input v-model="tenantName" type="text" autocomplete="organization" required />
        </label>
        <label>
          <span>Email</span>
          <input v-model="email" type="email" autocomplete="email" required />
        </label>
        <label>
          <span>Password</span>
          <input
            v-model="password"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required
          />
        </label>
        <label>
          <span>Your name <small>optional</small></span>
          <input v-model="displayName" type="text" autocomplete="name" />
        </label>
        <p v-if="authStore.error" class="field-error" role="alert">{{ authStore.error }}</p>
        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? "Creating workspace..." : "Create workspace" }}
        </button>
      </form>
      <p class="auth-switch">
        Already have an account? <router-link to="/login">Sign in</router-link>
      </p>
    </section>
  </main>
</template>
