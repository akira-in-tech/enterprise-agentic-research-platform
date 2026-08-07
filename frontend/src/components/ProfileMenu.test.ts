import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ProfileMenu from "./ProfileMenu.vue";

describe("ProfileMenu", () => {
  it("shows the account identity and emits edit-profile", async () => {
    const wrapper = mount(ProfileMenu, {
      props: {
        userDisplayName: "ACME Engineer",
        userEmail: "engineer@acme.example",
        tenantName: "ACME Platform",
        initials: "AE",
      },
    });

    const trigger = wrapper.get('[aria-haspopup="menu"]');
    expect(trigger.text()).toBe("AE");
    expect(trigger.attributes("aria-expanded")).toBe("false");

    await trigger.trigger("click");

    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(wrapper.text()).toContain("ACME Engineer");
    expect(wrapper.text()).toContain("engineer@acme.example");
    expect(wrapper.text()).toContain("ACME Platform");

    await wrapper.get('[role="menuitem"]').trigger("click");

    expect(wrapper.emitted("editProfile")).toHaveLength(1);
    expect(trigger.attributes("aria-expanded")).toBe("false");
  });

  it("emits logout from the second menu item", async () => {
    const wrapper = mount(ProfileMenu, {
      props: {
        userDisplayName: null,
        userEmail: "engineer@acme.example",
        tenantName: "ACME Platform",
        initials: "?",
      },
    });

    await wrapper.get('[aria-haspopup="menu"]').trigger("click");
    const items = wrapper.findAll('[role="menuitem"]');
    await items[1]?.trigger("click");

    expect(wrapper.emitted("logout")).toHaveLength(1);
  });

  it("falls back to the email when there is no display name", async () => {
    const wrapper = mount(ProfileMenu, {
      props: {
        userDisplayName: null,
        userEmail: "engineer@acme.example",
        tenantName: "ACME Platform",
        initials: "?",
      },
    });

    await wrapper.get('[aria-haspopup="menu"]').trigger("click");

    expect(wrapper.get(".profile-copy strong").text()).toBe("engineer@acme.example");
  });
});
