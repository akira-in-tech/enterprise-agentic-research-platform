import { defineStore } from "pinia";
import { ref } from "vue";

import type { WorkspaceContext } from "../types/research";

const WORKSPACE_KEY = "evident.workspace.v1";
const THEME_KEY = "evident.theme.v1";

function applyTheme(darkMode: boolean): void {
  document.documentElement.dataset.theme = darkMode ? "dark" : "light";
  document.documentElement.style.colorScheme = darkMode ? "dark" : "light";
}

export const useWorkspaceStore = defineStore("workspace", () => {
  const workspace = ref<WorkspaceContext>({
    tenantId: import.meta.env.VITE_TENANT_ID ?? "",
    userId: import.meta.env.VITE_USER_ID ?? "",
  });
  const darkMode = ref(false);
  const dialogOpen = ref(false);

  function hydrate(): void {
    const savedWorkspace = localStorage.getItem(WORKSPACE_KEY);
    if (savedWorkspace) {
      try {
        workspace.value = JSON.parse(savedWorkspace) as WorkspaceContext;
      } catch {
        localStorage.removeItem(WORKSPACE_KEY);
      }
    }

    darkMode.value = localStorage.getItem(THEME_KEY) === "dark";
    applyTheme(darkMode.value);
  }

  function isConfigured(): boolean {
    return workspace.value.tenantId.trim().length > 0;
  }

  function save(next: WorkspaceContext): void {
    workspace.value = next;
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(next));
    dialogOpen.value = false;
  }

  function openDialog(): void {
    dialogOpen.value = true;
  }

  function closeDialog(): void {
    dialogOpen.value = false;
  }

  function toggleTheme(): void {
    darkMode.value = !darkMode.value;
    localStorage.setItem(THEME_KEY, darkMode.value ? "dark" : "light");
    applyTheme(darkMode.value);
  }

  /** Test- and design-preview-only override, bypassing localStorage. */
  function setForPreview(next: WorkspaceContext): void {
    workspace.value = next;
  }

  return {
    workspace,
    darkMode,
    dialogOpen,
    hydrate,
    isConfigured,
    save,
    toggleTheme,
    setForPreview,
    openDialog,
    closeDialog,
  };
});
