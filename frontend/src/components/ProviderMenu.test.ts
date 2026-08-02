import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ProviderMenu from "./ProviderMenu.vue";

describe("ProviderMenu", () => {
  it("explains provider tradeoffs and emits an explicit selection", async () => {
    const wrapper = mount(ProviderMenu, {
      props: { modelValue: "qwen" },
    });

    const trigger = wrapper.get('[aria-haspopup="listbox"]');
    expect(trigger.attributes("aria-expanded")).toBe("false");
    await trigger.trigger("click");

    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(wrapper.text()).toContain("Private, no usage cost");
    expect(wrapper.text()).toContain("Stronger synthesis, usage billed");

    const options = wrapper.findAll('[role="option"]');
    await options[1]?.trigger("click");

    expect(wrapper.emitted("update:modelValue")).toEqual([["claude"]]);
  });

  it("exposes the selected provider to assistive technology", async () => {
    const wrapper = mount(ProviderMenu, {
      props: { modelValue: "claude" },
    });

    await wrapper.get('[aria-haspopup="listbox"]').trigger("click");
    const options = wrapper.findAll('[role="option"]');

    expect(options[0]?.attributes("aria-selected")).toBe("false");
    expect(options[1]?.attributes("aria-selected")).toBe("true");
  });

  it("does not offer local Qwen when the cloud build enables only Claude", async () => {
    const wrapper = mount(ProviderMenu, {
      props: { modelValue: "claude", enabledProviders: ["claude"] },
    });

    await wrapper.get('[aria-haspopup="listbox"]').trigger("click");

    expect(wrapper.findAll('[role="option"]')).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Qwen Local");
    expect(wrapper.text()).toContain("Claude Cloud");
  });
});
