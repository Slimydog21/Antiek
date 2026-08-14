/**
 * useFaviconAttention.test.ts — the pure dot-color decision (the canvas
 * painting itself is not unit-tested).
 */
import { describe, expect, it } from "vitest";

import { dotColorFor } from "./useFaviconAttention";

describe("dotColorFor", () => {
  it("blocked outranks unread", () => {
    expect(dotColorFor(1, 3)).toBe("blocked");
    expect(dotColorFor(2, 0)).toBe("blocked");
  });

  it("unread shows when nothing is blocked", () => {
    expect(dotColorFor(0, 1)).toBe("unread");
  });

  it("no attention means no dot", () => {
    expect(dotColorFor(0, 0)).toBeNull();
  });
});
