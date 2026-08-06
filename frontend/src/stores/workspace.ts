import { defineStore } from "pinia";
import { ref } from "vue";

const THEME_KEY = "evident.theme.v1";

function applyTheme(darkMode: boolean): void {
  document.documentElement.dataset.theme = darkMode ? "dark" : "light";
  document.documentElement.style.colorScheme = darkMode ? "dark" : "light";
}

export const useWorkspaceStore = defineStore("workspace", () => {
  const darkMode = ref(false);

  function hydrate(): void {
    darkMode.value = localStorage.getItem(THEME_KEY) === "dark";
    applyTheme(darkMode.value);
  }

  function toggleTheme(): void {
    darkMode.value = !darkMode.value;
    localStorage.setItem(THEME_KEY, darkMode.value ? "dark" : "light");
    applyTheme(darkMode.value);
  }

  return {
    darkMode,
    hydrate,
    toggleTheme,
  };
});
