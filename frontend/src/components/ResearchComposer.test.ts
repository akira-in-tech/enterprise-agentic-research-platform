import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ResearchComposer from "./ResearchComposer.vue";

const readyDocument = {
  id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
  tenant_id: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
  uploaded_by_user_id: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
  filename: "architecture.md",
  media_type: "text/markdown",
  byte_size: 128,
  content_sha256: "a".repeat(64),
  status: "ready",
  error_message: null,
  created_at: "2026-08-05T12:00:00Z",
  updated_at: "2026-08-05T12:00:00Z",
  indexed_at: "2026-08-05T12:00:00Z",
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify([readyDocument]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("ResearchComposer", () => {
  it("keeps the primary action disabled until the question is meaningful", async () => {
    const wrapper = mount(ResearchComposer, {
      props: {
        query: "",
        provider: "qwen",
        submitting: false,
        selectedDocumentIds: [],
      },
    });

    expect(wrapper.get('button[type="submit"]').attributes()).toHaveProperty("disabled");
    await wrapper.setProps({ query: "Compare PostgreSQL isolation levels." });
    expect(wrapper.get('button[type="submit"]').attributes()).not.toHaveProperty("disabled");
  });

  it("lets the user scope research to a selected private document", async () => {
    const wrapper = mount(ResearchComposer, {
      props: {
        query: "Question",
        provider: "qwen",
        submitting: false,
        selectedDocumentIds: [],
      },
    });

    await wrapper.get('button[aria-haspopup="dialog"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("architecture.md");

    await wrapper.get('input[type="checkbox"]').trigger("change");

    expect(wrapper.emitted("update:selectedDocumentIds")).toEqual([[[readyDocument.id]]]);
  });

  it("shows a selection count badge once documents are scoped", () => {
    const wrapper = mount(ResearchComposer, {
      props: {
        query: "Question",
        provider: "qwen",
        submitting: false,
        selectedDocumentIds: [readyDocument.id],
      },
    });

    expect(wrapper.get(".knowledge-count-badge").text()).toBe("1");
  });
});
