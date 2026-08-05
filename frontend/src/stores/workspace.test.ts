import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspaceStore } from "./workspace";

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("useWorkspaceStore", () => {
  it("starts unconfigured until a workspace is saved", () => {
    const store = useWorkspaceStore();

    expect(store.isConfigured()).toBe(false);

    store.save({ tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901", userId: "" });

    expect(store.isConfigured()).toBe(true);
    expect(store.dialogOpen).toBe(false);
  });

  it("persists a saved workspace to localStorage and restores it on hydrate", () => {
    const store = useWorkspaceStore();
    store.save({ tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901", userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d" });

    const rehydrated = useWorkspaceStore();
    rehydrated.workspace = { tenantId: "", userId: "" };
    rehydrated.hydrate();

    expect(rehydrated.workspace).toEqual({
      tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
      userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
    });
  });

  it("discards an unparsable saved workspace instead of throwing", () => {
    localStorage.setItem("evident.workspace.v1", "{not json");
    const store = useWorkspaceStore();

    expect(() => store.hydrate()).not.toThrow();
    expect(localStorage.getItem("evident.workspace.v1")).toBeNull();
  });

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

  it("opens and closes the workspace dialog", () => {
    const store = useWorkspaceStore();

    store.openDialog();
    expect(store.dialogOpen).toBe(true);

    store.closeDialog();
    expect(store.dialogOpen).toBe(false);
  });

  it("sets a preview workspace without touching localStorage", () => {
    const store = useWorkspaceStore();
    store.setForPreview({ tenantId: "preview-tenant", userId: "preview-user" });

    expect(store.workspace).toEqual({ tenantId: "preview-tenant", userId: "preview-user" });
    expect(localStorage.getItem("evident.workspace.v1")).toBeNull();
  });
});
