/**
 * crossfadeMachine.test.ts — the interruptible crossfade INVARIANTS (ALC SPR-06
 * M3), proven on the PURE reducer (no DOM, no time, no React) — rigor #3's
 * "interruption smoothness as a state-machine test, not eyeballed."
 *
 * The contract the machine must hold (and that SPR-07/08 must not break):
 *   1. A new art flips the front slot; the new front targets painted, the old
 *      front targets 0 (a cross-dissolve).
 *   2. INTERRUPTION = RETARGET FROM CURRENT, NEVER QUEUE. A second new art
 *      mid-fade does NOT wait for the first fade to finish — it immediately
 *      becomes the front. There is no pending queue; the latest art always wins.
 *   3. The slots are PERSISTENT — the same two slot ids (A/B) recur; a flip
 *      changes a slot's url + target, it never invents a third slot (the DOM
 *      stability that makes a CSS transition retarget instead of restart).
 *   4. Same art re-dispatched → no-op (no spurious re-fade).
 *   5. Fallback (null) → both slots release toward 0 (clean release, not a cut).
 */
import { describe, expect, it } from "vitest";

import {
  initCrossfade,
  crossfadeReduce,
  type CrossfadeState,
} from "./crossfadeMachine";

const PAINTED = 0.82;
const opts = { paintedOpacity: PAINTED };
const reduce = (s: CrossfadeState, url: string | null) => crossfadeReduce(s, url, opts);

/** The slot currently targeting `painted` (the front), or null if none. */
function frontOf(s: CrossfadeState): { id: "A" | "B"; url: string | null } | null {
  for (const id of ["A", "B"] as const) {
    if (s[id].target === PAINTED) return { id, url: s[id].url };
  }
  return null;
}

describe("crossfadeMachine — first art", () => {
  it("flips the front and targets painted; the other slot stays at 0", () => {
    const s = reduce(initCrossfade(), "art/1.png");
    const front = frontOf(s);
    expect(front).toBeTruthy();
    expect(front!.url).toBe("art/1.png");
    // Exactly one slot painted.
    const painted = (["A", "B"] as const).filter((id) => s[id].target === PAINTED);
    expect(painted).toHaveLength(1);
  });
});

describe("crossfadeMachine — INTERRUPTION: retarget from current, never queue", () => {
  it("a mid-fade new art immediately becomes the front (no queue); the old front releases to 0", () => {
    let s = reduce(initCrossfade(), "art/1.png");
    const firstFront = frontOf(s)!;
    // Simulate the visual being MID-FADE (the DOM would be at some 0<opacity<painted;
    // the machine tracks TARGETS, the browser interpolates from current). Now flip.
    s = reduce(s, "art/2.png");

    const newFront = frontOf(s)!;
    // The new art is the front NOW — it did not wait for art/1 to finish.
    expect(newFront.url).toBe("art/2.png");
    // The front slot CHANGED id (the two slots swapped roles — persistent slots).
    expect(newFront.id).not.toBe(firstFront.id);
    // The previous front is now releasing toward 0.
    expect(s[firstFront.id].target).toBe(0);
    expect(s[firstFront.id].url).toBe("art/1.png"); // still painting art/1 as it fades out
  });

  it("a BURST of flips collapses to the latest art on the front (no stutter of queued fades)", () => {
    let s = initCrossfade();
    for (const url of ["a.png", "b.png", "c.png", "d.png", "e.png"]) {
      s = reduce(s, url);
    }
    const front = frontOf(s)!;
    expect(front.url).toBe("e.png"); // the LATEST wins; nothing queued
    // Still only two slots, only one painted.
    const painted = (["A", "B"] as const).filter((id) => s[id].target === PAINTED);
    expect(painted).toHaveLength(1);
  });

  it("the two slots alternate as the front across successive flips (persistent A/B, never a third)", () => {
    let s = initCrossfade();
    s = reduce(s, "1.png");
    const f1 = frontOf(s)!.id;
    s = reduce(s, "2.png");
    const f2 = frontOf(s)!.id;
    s = reduce(s, "3.png");
    const f3 = frontOf(s)!.id;
    expect(f1).not.toBe(f2);
    expect(f2).not.toBe(f3);
    expect(f3).toBe(f1); // A→B→A — exactly two slots recycled
  });
});

describe("crossfadeMachine — no spurious re-fade", () => {
  it("re-dispatching the SAME front art is a no-op (identical state reference)", () => {
    const s1 = reduce(initCrossfade(), "same.png");
    const s2 = reduce(s1, "same.png");
    expect(s2).toBe(s1); // referential no-op → React won't re-render / re-fade
  });
});

describe("crossfadeMachine — fallback release", () => {
  it("null art releases BOTH slots toward 0 (clean release, not a cut)", () => {
    let s = reduce(initCrossfade(), "live.png");
    s = reduce(s, null);
    expect(s.A.target).toBe(0);
    expect(s.B.target).toBe(0);
    // The slot still remembers its url so it can FADE out (not vanish instantly).
    const stillPainting = (["A", "B"] as const).some((id) => s[id].url === "live.png");
    expect(stillPainting).toBe(true);
  });

  it("re-show after fallback brings art back to a front slot (a fade-in, not a snap)", () => {
    let s = reduce(initCrossfade(), "live.png");
    s = reduce(s, null); // released
    s = reduce(s, "live2.png"); // art returns
    const front = frontOf(s)!;
    expect(front.url).toBe("live2.png");
  });

  it("null when already released is a no-op", () => {
    const released = reduce(reduce(initCrossfade(), "x.png"), null);
    const again = reduce(released, null);
    expect(again).toBe(released);
  });
});
