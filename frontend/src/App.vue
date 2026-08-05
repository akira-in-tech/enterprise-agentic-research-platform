<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";

import AppHeader from "./components/AppHeader.vue";
import WorkspaceDialog from "./components/WorkspaceDialog.vue";
import { useResearchStore } from "./stores/research";
import { useWorkspaceStore } from "./stores/workspace";
import type { WorkspaceContext } from "./types/research";

const route = useRoute();
const router = useRouter();
const researchStore = useResearchStore();
const workspaceStore = useWorkspaceStore();

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

function saveWorkspace(next: WorkspaceContext): void {
  workspaceStore.save(next);
  researchStore.announcement = "Workspace context saved.";
}
</script>

<template>
  <a v-if="!researchStore.designPreview" class="skip-link" href="#main">Skip to main content</a>
  <div class="app-shell">
    <AppHeader
      :dark-mode="workspaceStore.darkMode"
      :api-status="researchStore.apiStatus"
      :workspace-configured="workspaceStore.isConfigured()"
      :active-page="activePage"
      workspace-name="Acme Analytics"
      @new-research="startNewResearch"
      @show-recent="startNewResearch"
      @show-knowledge="showKnowledge"
      @toggle-theme="workspaceStore.toggleTheme()"
      @open-workspace="workspaceStore.openDialog()"
    />

    <router-view />

    <footer class="app-footer">
      <span>All research and sources are scoped to Acme Analytics.</span>
      <span>You control access. You own the results.</span>
    </footer>
  </div>

  <WorkspaceDialog
    :open="workspaceStore.dialogOpen"
    :workspace="workspaceStore.workspace"
    @close="workspaceStore.closeDialog()"
    @save="saveWorkspace"
  />

  <p class="sr-only" aria-live="polite">{{ researchStore.announcement }}</p>
</template>
