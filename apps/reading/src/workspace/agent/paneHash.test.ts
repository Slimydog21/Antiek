/** paneHash.test.ts — SPR-07 invariant 31 (the Phase A half: parse/format; the deep-link mount is Phase B). */
import { describe, expect, it } from "vitest";

import { formatPaneHash, parsePaneHash } from "./paneHash";

describe("paneHash", () => {
  it("parses #pane=agent:<id> and formats it back", () => {
    expect(parsePaneHash("#pane=agent:p:proj-1")).toEqual({ agentId: "p:proj-1" });
    expect(parsePaneHash("pane=agent:x:2")).toEqual({ agentId: "x:2" });
    expect(parsePaneHash("#pane=agent:")).toBeNull();
    expect(parsePaneHash("#other")).toBeNull();
    expect(parsePaneHash("")).toBeNull();
    expect(formatPaneHash("p:proj-1")).toBe("#pane=agent:p:proj-1");
    expect(parsePaneHash(formatPaneHash("p:a b"))).toEqual({ agentId: "p:a b" });
  });
});
