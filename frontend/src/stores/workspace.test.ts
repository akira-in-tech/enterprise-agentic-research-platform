import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspaceStore } from "./workspace";

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("useWorkspaceStore", () => {
  it("toggles and persists the theme, applying it to the document root", () => {
    const store = useWorkspaceStore();

    store.toggleTheme();

    expect(store.darkMode).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("evident.theme.v1")).toBe("dark");

    store.toggleTheme();

    expect(store.darkMode).toBe(false);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("restores the persisted theme on hydrate", () => {
    localStorage.setItem("evident.theme.v1", "dark");
    const store = useWorkspaceStore();

    store.hydrate();

    expect(store.darkMode).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
