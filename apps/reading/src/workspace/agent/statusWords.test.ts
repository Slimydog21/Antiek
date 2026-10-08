/** statusWords.test.ts — SPR-07 invariant 20. */
import { describe, expect, it } from "vitest";

import { STATUS_WORDS, statusWordFor, statusLabel } from "./statusWords";

describe("statusWords", () => {
  it("is Antiek-authored, five words, deterministic by turn index", () => {
    expect(STATUS_WORDS).toEqual(["reading", "weighing", "drafting", "checking", "answering"]);
    for (let i = 0; i < 10; i++) expect(statusWordFor(i)).toBe(STATUS_WORDS[i % 5]);
  });

  it("present tense while pending/streaming; past tense when done or failed", () => {
    expect(statusLabel("pending", 0)).toBe("reading");
    expect(statusLabel("streaming", 1)).toBe("weighing");
    expect(statusLabel("done", 2)).toBe("answered");
    expect(statusLabel("failed", 3)).toBe("couldn't answer");
  });
});
