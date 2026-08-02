import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ProviderComparison from "./ProviderComparison.vue";

describe("ProviderComparison", () => {
  it("keeps the provider tradeoff visible and emits an explicit selection", async () => {
    const wrapper = mount(ProviderComparison, {
      props: { modelValue: "qwen" },
    });

    const radios = wrapper.findAll('input[type="radio"]');
    expect(radios).toHaveLength(2);
    expect(wrapper.text()).toContain("Maximum privacy");
    expect(wrapper.text()).toContain("Higher cost");

    await radios[1]?.setValue();
    expect(wrapper.emitted("update:modelValue")).toEqual([["claude"]]);
  });
});
