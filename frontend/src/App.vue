<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";

import AppHeader from "./components/AppHeader.vue";
import { useAuthStore } from "./stores/auth";
import { useResearchStore } from "./stores/research";
import { useWorkspaceStore } from "./stores/workspace";

const route = useRoute();
const router = useRouter();
const researchStore = useResearchStore();
const workspaceStore = useWorkspaceStore();
const authStore = useAuthStore();

const activePage = computed<"research" | "knowledge">(() =>
  route.name === "knowledge" ? "knowledge" : "research",
);

onMounted(() => {
  workspaceStore.hydrate();
  researchStore.hydrate();
  if (researchStore.designPreview) {
    researchStore.applyDesignPreviewIssue();
  }
});

function startNewResearch(): void {
  researchStore.resetActiveRun();
  void router.push({ name: "home" });
}

function showKnowledge(): void {
  researchStore.resetActiveRun();
  void router.push({ name: "knowledge" });
}

async function logout(): Promise<void> {
  await authStore.logout();
  await router.push({ name: "login" });
}
</script>

<template>
  <a v-if="!researchStore.designPreview" class="skip-link" href="#main">Skip to main content</a>
  <div class="app-shell">
    <AppHeader
      v-if="authStore.isAuthenticated()"
      :dark-mode="workspaceStore.darkMode"
      :api-status="researchStore.apiStatus"
      :tenant-name="authStore.tenant?.name ?? ''"
      :user-display-name="authStore.user?.display_name ?? null"
      :active-page="activePage"
      @new-research="startNewResearch"
      @show-recent="startNewResearch"
      @show-knowledge="showKnowledge"
      @toggle-theme="workspaceStore.toggleTheme()"
      @logout="logout"
    />

    <router-view />

    <footer v-if="authStore.isAuthenticated()" class="app-footer">
      <span>All research and sources are scoped to {{ authStore.tenant?.name }}.</span>
      <span>You control access. You own the results.</span>
    </footer>
  </div>

  <p class="sr-only" aria-live="polite">{{ researchStore.announcement }}</p>
</template>
