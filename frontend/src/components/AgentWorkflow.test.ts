import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AgentWorkflow from "./AgentWorkflow.vue";

describe("AgentWorkflow", () => {
  it("presents all eight agents in a stable accessible order", () => {
    const wrapper = mount(AgentWorkflow, {
      props: { activeAgent: "analyze" },
    });

    const steps = wrapper.findAll(".agent-step");
    expect(steps).toHaveLength(8);
    expect(steps.map((step) => step.text())).toEqual([
      "Scope",
      "Plan",
      "Retrieve",
      "Private RAG",
      "AnalyzeWorking",
      "Verify",
      "Synthesize",
      "Report",
    ]);
    expect(wrapper.get('[aria-current="step"]').text()).toContain("Analyze");
  });

  it("marks the whole flow complete without leaving an active step", () => {
    const wrapper = mount(AgentWorkflow, {
      props: { completed: true },
    });

    expect(wrapper.find('[aria-current="step"]').exists()).toBe(false);
    expect(wrapper.findAll(".agent-complete")).toHaveLength(8);
  });
});
