/**
 * WernerStage.test.ts — the imperative command controller (SPR-05 / SPR-10).
 *
 * A FAKE StageHost records the calls the controller makes (walkTo / setEmote /
 * setRoamPaused / setFollowing) and an INJECTED timers stub makes the
 * sequencing deterministic — no React, no real clock. Load-bearing claims:
 *  - moveTo → waddling, pauses roam, walks, resumes on arrival;
 *  - waddleToEl(el) → walk to the element CENTER → hit emote → idle, resuming
 *    roam; the walk-target math is asserted (center of the rect), not eyeballed;
 *  - missing / zero-size / off-screen target → graceful no-op (no throw, no
 *    walk);
 *  - rapid commands are latest-wins (one timer, the old one cleared);
 *  - frozen (reduced motion): no directed walk — waddleToEl downshifts to a
 *    small in-place emote; moveTo/follow are no-ops.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createWernerStage,
  type StageHost,
  type WernerStageController,
} from "./WernerStage";
import { emoteDurationMs } from "./emotes";

// A controllable timer queue: setTimeout records (fn, ms, id); we fire by id
// or "run the next due". This proves latest-wins by checking the old id is
// cleared before a new one is scheduled.
function makeTimers() {
  let nextId = 1;
  const pending = new Map<number, () => void>();
  return {
    api: {
      setTimeout: (fn: () => void, _ms: number) => {
        const id = nextId++;
        pending.set(id, fn);
        return id;
      },
      clearTimeout: (id: number) => {
        pending.delete(id);
      },
    },
    /** Fire every currently-pending callback (FIFO). */
    flush() {
      // Snapshot: a callback may schedule a follow-up (waddle → emote chain).
      const ids = [...pending.keys()];
      for (const id of ids) {
        const fn = pending.get(id);
        pending.delete(id);
        fn?.();
      }
    },
    /** Fire callbacks repeatedly until the queue is empty (chained actions). */
    drain() {
      let guard = 0;
      while (pending.size && guard++ < 20) this.flush();
    },
    size: () => pending.size,
  };
}

function makeHost() {
  const calls: string[] = [];
  let pos = { x: 50, y: 50 };
  const host: StageHost = {
    walkTo: (x, y) => {
      pos = { x, y };
      calls.push(`walkTo(${x},${y})`);
    },
    getPos: () => pos,
    setEmote: (k) => calls.push(`emote(${k ?? "null"})`),
    setFollowing: (on) => calls.push(`following(${on})`),
    setRoamPaused: (p) => calls.push(`roamPaused(${p})`),
  };
  return { host, calls, getPos: () => pos };
}

function fakeEl(rect: Partial<DOMRect>): Element {
  return {
    getBoundingClientRect: () =>
      ({
        left: 0,
        top: 0,
        width: 0,
        height: 0,
        right: 0,
        bottom: 0,
        x: 0,
        y: 0,
        ...rect,
      }) as DOMRect,
  } as Element;
}

let stage: WernerStageController;
let timers: ReturnType<typeof makeTimers>;
let host: ReturnType<typeof makeHost>;

beforeEach(() => {
  // jsdom default viewport is 1024x768; pin a known one for off-screen math.
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
  timers = makeTimers();
  host = makeHost();
  stage = createWernerStage(host.host, timers.api);
});

describe("createWernerStage", () => {
  it("moveTo pauses roam, walks, then resumes on arrival → idle", () => {
    stage.moveTo(300, 400);
    expect(stage.getState().name).toBe("waddling");
    expect(host.calls).toContain("roamPaused(true)");
    expect(host.calls).toContain("walkTo(300,400)");
    timers.drain();
    expect(stage.getState().name).toBe("idle");
    expect(host.calls).toContain("roamPaused(false)");
  });

  it("waddleToEl walks to the element CENTER, plays hit, returns to idle (target math asserted)", () => {
    // Rect 200..400 x, 100..300 y → center (300, 200).
    const el = fakeEl({ left: 200, top: 100, width: 200, height: 200, right: 400, bottom: 300 });
    stage.waddleToEl(el, "hit");
    expect(stage.getState().name).toBe("waddling");
    expect(host.calls).toContain("walkTo(300,200)");
    timers.drain();
    // Walk → emote(hit) → emote(null) → idle.
    expect(host.calls).toContain("emote(hit)");
    expect(host.calls).toContain("emote(null)");
    expect(stage.getState().name).toBe("idle");
    expect(host.calls).toContain("roamPaused(false)");
  });

  it("missing target → graceful no-op (no walk, no throw, stays idle)", () => {
    expect(() => stage.waddleToEl(null)).not.toThrow();
    expect(host.calls.some((c) => c.startsWith("walkTo"))).toBe(false);
    expect(stage.getState().name).toBe("idle");
  });

  it("zero-size target → no-op (display:none / detached element)", () => {
    stage.waddleToEl(fakeEl({ width: 0, height: 0 }));
    expect(host.calls.some((c) => c.startsWith("walkTo"))).toBe(false);
    expect(stage.getState().name).toBe("idle");
  });

  it("off-screen target (center past the viewport) → no-op", () => {
    // Center at (5000, 5000), well past 1200x800.
    const el = fakeEl({ left: 4900, top: 4900, width: 200, height: 200, right: 5100, bottom: 5100 });
    stage.waddleToEl(el);
    expect(host.calls.some((c) => c.startsWith("walkTo"))).toBe(false);
    expect(stage.getState().name).toBe("idle");
  });

  it("latest-wins: a second command clears the first's timer (no stacked waddles)", () => {
    stage.moveTo(100, 100);
    const after1 = timers.size();
    expect(after1).toBe(1); // one action timer pending
    stage.moveTo(700, 700); // supersede
    // Still exactly one pending timer — the old was cleared, not queued.
    expect(timers.size()).toBe(1);
    timers.drain();
    // Landed at the LAST target.
    expect(host.getPos()).toEqual({ x: 700, y: 700 });
    expect(stage.getState().name).toBe("idle");
  });

  it("emote alone plays then resumes the ambient state", () => {
    stage.follow(true);
    expect(stage.getState().name).toBe("following");
    stage.emote("happy");
    expect(stage.getState().name).toBe("emoting");
    timers.drain();
    // Resumes FOLLOWING, not a hard idle.
    expect(stage.getState().name).toBe("following");
  });

  it("frozen: moveTo / follow are no-ops; waddleToEl downshifts to an in-place emote", () => {
    stage.freeze();
    expect(stage.getState().name).toBe("frozen");
    stage.moveTo(300, 300);
    expect(host.calls.some((c) => c.startsWith("walkTo"))).toBe(false);
    expect(stage.getState().name).toBe("frozen");

    const el = fakeEl({ left: 200, top: 100, width: 200, height: 200, right: 400, bottom: 300 });
    stage.waddleToEl(el, "hit");
    // No screen-crossing walk — just the still acknowledgment emote.
    expect(host.calls.some((c) => c.startsWith("walkTo"))).toBe(false);
    expect(host.calls).toContain("emote(hit)");
    timers.drain();
    expect(host.calls).toContain("emote(null)"); // still emote cleared after the beat
    expect(stage.getState().name).toBe("frozen"); // never left the floor
  });

  it("unfreeze returns to idle and re-enables directed motion", () => {
    stage.freeze();
    stage.unfreeze();
    expect(stage.getState().name).toBe("idle");
    stage.moveTo(300, 300);
    expect(host.calls).toContain("walkTo(300,300)");
  });

  it("emote durations come from the emote table", () => {
    const spy = vi.fn();
    const t = {
      setTimeout: (_fn: () => void, ms: number) => {
        spy(ms);
        return 1;
      },
      clearTimeout: () => {},
    };
    const s = createWernerStage(host.host, t);
    s.emote("sleeping");
    expect(spy).toHaveBeenCalledWith(emoteDurationMs("sleeping"));
  });
});
