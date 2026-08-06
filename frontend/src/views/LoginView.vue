<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();

const email = ref("");
const password = ref("");
const submitting = ref(false);

async function submit(): Promise<void> {
  submitting.value = true;

  try {
    const success = await authStore.login({
      email: email.value.trim(),
      password: password.value,
    });

    if (success) {
      const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
      await router.push(redirect);
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main id="main" class="auth-page" tabindex="-1">
    <section class="auth-card" aria-labelledby="login-title">
      <p class="eyebrow">Welcome back</p>
      <h1 id="login-title">Sign in</h1>
      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>Email</span>
          <input v-model="email" type="email" autocomplete="email" required />
        </label>
        <label>
          <span>Password</span>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="authStore.error" class="field-error" role="alert">{{ authStore.error }}</p>
        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? "Signing in..." : "Sign in" }}
        </button>
      </form>
      <p class="auth-switch">Don't have an account? <router-link to="/register">Create one</router-link></p>
    </section>
  </main>
</template>
