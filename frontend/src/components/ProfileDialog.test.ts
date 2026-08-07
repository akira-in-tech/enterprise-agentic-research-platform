import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../stores/auth";
import ProfileDialog from "./ProfileDialog.vue";

const identity = {
  user: {
    id: "user-1",
    email: "engineer@acme.example",
    display_name: "ACME Engineer",
  },
  tenant: {
    id: "tenant-1",
    name: "ACME Platform",
    slug: "acme-platform-a1b2c3d4",
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().setForPreview(identity);
});

afterEach(() => vi.unstubAllGlobals());

describe("ProfileDialog", () => {
  it("pre-fills the current display name", () => {
    const wrapper = mount(ProfileDialog);

    const input = wrapper.get('input[autocomplete="name"]').element as HTMLInputElement;
    expect(input.value).toBe("ACME Engineer");
  });

  it("saves a new display name and shows confirmation", async () => {
    const renamed = { ...identity, user: { ...identity.user, display_name: "New Name" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(renamed)));
    const wrapper = mount(ProfileDialog);

    await wrapper.get('input[autocomplete="name"]').setValue("New Name");
    await wrapper.get("form").trigger("submit");
    await wrapper.vm.$nextTick();
    await new Promise((resolve) => setTimeout(resolve));
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("Display name updated.");
    expect(useAuthStore().user?.display_name).toBe("New Name");
  });

  it("shows a local error when the new password confirmation does not match", async () => {
    const wrapper = mount(ProfileDialog);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const [currentPassword, newPassword, confirmPassword] =
      wrapper.findAll('input[type="password"]');
    await currentPassword?.setValue("correct-horse-battery");
    await newPassword?.setValue("new-correct-horse-battery");
    await confirmPassword?.setValue("does-not-match");
    await wrapper.findAll("form")[1]?.trigger("submit");

    expect(wrapper.text()).toContain("do not match");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("changes the password and clears the fields on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const wrapper = mount(ProfileDialog);

    const [currentPassword, newPassword, confirmPassword] =
      wrapper.findAll('input[type="password"]');
    await currentPassword?.setValue("correct-horse-battery");
    await newPassword?.setValue("new-correct-horse-battery");
    await confirmPassword?.setValue("new-correct-horse-battery");
    await wrapper.findAll("form")[1]?.trigger("submit");
    await wrapper.vm.$nextTick();
    await new Promise((resolve) => setTimeout(resolve));
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("Password changed.");
    expect((currentPassword?.element as HTMLInputElement).value).toBe("");
  });

  it("emits close from the close button", async () => {
    const wrapper = mount(ProfileDialog);

    await wrapper.get(".dialog-close").trigger("click");

    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("emits close when the backdrop itself is clicked", async () => {
    const wrapper = mount(ProfileDialog);

    await wrapper.get(".dialog-backdrop").trigger("click");

    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("does not close when clicking inside the dialog card", async () => {
    const wrapper = mount(ProfileDialog);

    await wrapper.get(".workspace-dialog").trigger("click");

    expect(wrapper.emitted("close")).toBeUndefined();
  });
});
