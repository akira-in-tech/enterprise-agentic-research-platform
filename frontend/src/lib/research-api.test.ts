import { describe, expect, it } from "vitest";

import { parseSseFrames } from "./research-api";

describe("parseSseFrames", () => {
  it("parses complete progress events and retains an incomplete frame", () => {
    const parsed = parseSseFrames(
      'event: progress\ndata: {"status":"running"}\n\nevent: progress\ndata: {"status"',
    );

    expect(parsed.frames).toEqual([
      {
        event: "progress",
        data: '{"status":"running"}',
      },
    ]);
    expect(parsed.remainder).toBe('event: progress\ndata: {"status"');
  });

  it("supports CRLF and multi-line data", () => {
    const parsed = parseSseFrames("event: error\r\ndata: first\r\ndata: second\r\n\r\n");

    expect(parsed.frames).toEqual([{ event: "error", data: "first\nsecond" }]);
    expect(parsed.remainder).toBe("");
  });
});
