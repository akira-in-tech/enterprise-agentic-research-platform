import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import KnowledgeLibrary from "./KnowledgeLibrary.vue";

const document = {
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

beforeEach(() => setActivePinia(createPinia()));
afterEach(() => vi.unstubAllGlobals());

describe("KnowledgeLibrary", () => {
  it("loads ready documents and uses a two-step delete confirmation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify([document]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(KnowledgeLibrary);
    await flushPromises();

    expect(wrapper.text()).toContain("architecture.md");
    expect(wrapper.text()).toContain("Ready");

    const deleteButton = wrapper.get('button[aria-label="Delete architecture.md"]');
    await deleteButton.trigger("click");
    expect(wrapper.text()).toContain("Confirm");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await wrapper.get('button[aria-label="Confirm deletion of architecture.md"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).not.toContain("architecture.md");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows an explicit recoverable error when listing fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Document storage is unavailable." }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const wrapper = mount(KnowledgeLibrary);
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("Document storage is unavailable.");
    expect(wrapper.text()).toContain("Retry");
  });
});
