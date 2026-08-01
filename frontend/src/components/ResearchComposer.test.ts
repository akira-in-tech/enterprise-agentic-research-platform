import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ResearchComposer from "./ResearchComposer.vue";

describe("ResearchComposer", () => {
  it("keeps the primary action disabled until the question is meaningful", async () => {
    const wrapper = mount(ResearchComposer, {
      props: {
        query: "",
        provider: "qwen",
        submitting: false,
      },
    });

    expect(wrapper.get('button[type="submit"]').attributes()).toHaveProperty("disabled");
    await wrapper.setProps({ query: "Compare PostgreSQL isolation levels." });
    expect(wrapper.get('button[type="submit"]').attributes()).not.toHaveProperty("disabled");
  });

  it("marks private knowledge as honestly unavailable", () => {
    const wrapper = mount(ResearchComposer, {
      props: {
        query: "Question",
        provider: "qwen",
        submitting: false,
      },
    });

    const privateKnowledge = wrapper.get('[aria-describedby="knowledge-help"]');
    expect(privateKnowledge.attributes()).toHaveProperty("disabled");
    expect(wrapper.get("#knowledge-help").text()).toContain("not yet exposed");
  });
});
