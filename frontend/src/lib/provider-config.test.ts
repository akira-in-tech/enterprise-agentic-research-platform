import { describe, expect, it } from "vitest";

import { parseEnabledProviders } from "./provider-config";

describe("parseEnabledProviders", () => {
  it("keeps both local providers enabled by default", () => {
    expect(parseEnabledProviders(undefined)).toEqual(["qwen", "claude"]);
  });

  it("supports a Claude-only cloud build", () => {
    expect(parseEnabledProviders("claude")).toEqual(["claude"]);
  });

  it("normalizes, filters, and deduplicates configured providers", () => {
    expect(parseEnabledProviders(" CLAUDE,unknown,claude,qwen ")).toEqual(["claude", "qwen"]);
  });

  it("rejects a configuration with no supported provider", () => {
    expect(() => parseEnabledProviders("unknown")).toThrow(
      "VITE_ENABLED_LLM_PROVIDERS must include qwen or claude.",
    );
  });
});
