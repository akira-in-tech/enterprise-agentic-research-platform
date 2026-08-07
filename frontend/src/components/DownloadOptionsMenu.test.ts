import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import DownloadOptionsMenu from "./DownloadOptionsMenu.vue";

describe("DownloadOptionsMenu", () => {
  it("lists all four format and citation-style combinations", async () => {
    const wrapper = mount(DownloadOptionsMenu);

    await wrapper.get('[aria-haspopup="listbox"]').trigger("click");

    const options = wrapper.findAll('[role="option"]');
    expect(options).toHaveLength(4);
    expect(wrapper.text()).toContain("Markdown · Numbered");
    expect(wrapper.text()).toContain("Markdown · Footnote");
    expect(wrapper.text()).toContain("PDF · Numbered");
    expect(wrapper.text()).toContain("PDF · Footnote");
  });

  it("emits the chosen format and citation style, then closes the menu", async () => {
    const wrapper = mount(DownloadOptionsMenu);

    await wrapper.get('[aria-haspopup="listbox"]').trigger("click");
    const options = wrapper.findAll('[role="option"]');
    await options[2]?.trigger("click");

    expect(wrapper.emitted("download")).toEqual([["pdf", "numbered"]]);
    expect(wrapper.get('[aria-haspopup="listbox"]').attributes("aria-expanded")).toBe("false");
  });

  it("emits the footnote markdown option correctly", async () => {
    const wrapper = mount(DownloadOptionsMenu);

    await wrapper.get('[aria-haspopup="listbox"]').trigger("click");
    const options = wrapper.findAll('[role="option"]');
    await options[1]?.trigger("click");

    expect(wrapper.emitted("download")).toEqual([["markdown", "footnote"]]);
  });

  it("disables the trigger and shows a preparing state while downloading", () => {
    const wrapper = mount(DownloadOptionsMenu, {
      props: { downloading: true },
    });

    const trigger = wrapper.get('[aria-haspopup="listbox"]');
    expect(trigger.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Preparing…");
  });
});
