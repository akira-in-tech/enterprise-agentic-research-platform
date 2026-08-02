import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import OperationalNotice from "./OperationalNotice.vue";

describe("OperationalNotice", () => {
  it("makes recovery explicit without hiding the failure reason", async () => {
    const wrapper = mount(OperationalNotice, {
      props: {
        issue: {
          kind: "redis_unavailable",
          title: "Redis is temporarily unavailable",
          message: "The request was not started.",
          actionLabel: "Try again",
        },
      },
    });

    expect(wrapper.attributes("role")).toBe("alert");
    expect(wrapper.text()).toContain("The request was not started.");
    await wrapper.get(".notice-action").trigger("click");
    await wrapper.get(".notice-dismiss").trigger("click");
    expect(wrapper.emitted("action")).toHaveLength(1);
    expect(wrapper.emitted("dismiss")).toHaveLength(1);
  });
});
