import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AgentWorkflow from "./AgentWorkflow.vue";

describe("AgentWorkflow", () => {
  it("presents all eight agents in a stable accessible order", () => {
    const wrapper = mount(AgentWorkflow, {
      props: { activeAgent: "analyst", status: "running" },
    });

    const steps = wrapper.findAll(".agent-step");
    expect(steps).toHaveLength(8);
    expect(steps.map((step) => step.text())).toEqual([
      "Intent Router",
      "Planner",
      "Web Scout",
      "Local Scout",
      "Evidence Judge",
      "AnalystWorking",
      "Reflect",
      "Writer",
    ]);
    expect(wrapper.get('[aria-current="step"]').text()).toContain("Analyst");
  });

  it("marks the whole flow complete without leaving an active step", () => {
    const wrapper = mount(AgentWorkflow, {
      props: { status: "completed" },
    });

    expect(wrapper.find('[aria-current="step"]').exists()).toBe(false);
    expect(wrapper.findAll(".agent-complete")).toHaveLength(8);
  });

  it("does not fake progress before a run has started", () => {
    const wrapper = mount(AgentWorkflow, {
      props: { status: "idle" },
    });

    expect(wrapper.find('[aria-current="step"]').exists()).toBe(false);
    expect(wrapper.findAll(".agent-complete")).toHaveLength(0);
    expect(wrapper.findAll(".agent-pending")).toHaveLength(8);
  });

  it("flags the step it stopped on when the run failed", () => {
    const wrapper = mount(AgentWorkflow, {
      props: { activeAgent: "analyst", status: "failed" },
    });

    const failedStep = wrapper.get(".agent-failed");
    expect(failedStep.text()).toContain("Analyst");
    expect(failedStep.text()).toContain("Needs attention");
    expect(wrapper.find('[aria-current="step"]').exists()).toBe(false);
    expect(wrapper.findAll(".agent-complete")).toHaveLength(5);
  });
});
