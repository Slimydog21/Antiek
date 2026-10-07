/** simulatedStream.test.ts — SPR-07 invariant 21. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { CHARS_PER_FRAME, simulateStream } from "./simulatedStream";

describe("simulateStream", () => {
  it("`immediate` emits the whole text once, synchronously", () => {
    const chunks: Array<[string, boolean]> = [];
    simulateStream("hello world", (sofar, done) => chunks.push([sofar, done]), { immediate: true });
    expect(chunks).toEqual([["hello world", true]]);
  });

  it("reduced motion is immediate too", () => {
    const chunks: Array<[string, boolean]> = [];
    simulateStream("abc", (sofar, done) => chunks.push([sofar, done]), { reducedMotion: true });
    expect(chunks).toEqual([["abc", true]]);
  });

  it("otherwise it grows by CHARS_PER_FRAME per frame and can be cancelled", () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { frames.push(cb); return frames.length; });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    try {
      const text = "x".repeat(CHARS_PER_FRAME * 2 + 1);
      const chunks: Array<[number, boolean]> = [];
      const cancel = simulateStream(text, (sofar, done) => chunks.push([sofar.length, done]), {});
      expect(chunks).toEqual([]);
      frames.shift()!(0);
      expect(chunks).toEqual([[CHARS_PER_FRAME, false]]);
      frames.shift()!(0);
      expect(chunks.at(-1)).toEqual([CHARS_PER_FRAME * 2, false]);
      cancel();
      frames.shift()?.(0);
      expect(chunks).toHaveLength(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("the source names itself a SIMULATED STREAM (fix 2)", () => {
    const src = readFileSync(resolve(__dirname, "simulatedStream.ts"), "utf8");
    expect(src).toContain("SIMULATED STREAM");
  });
});
