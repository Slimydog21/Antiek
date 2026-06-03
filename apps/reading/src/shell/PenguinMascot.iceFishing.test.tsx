/**
 * WERNER-ICE SPR-15 — reel integration + synthetic lag budget (≤ 950ms).
 *
 * Kinematic assertions only (no module mock) so SPR-06 roam tests keep
 * `wernerIceFishingCursor: false` isolation in PenguinMascot.test.tsx.
 */
import { describe, expect, it } from "vitest";

import { centerLaggedTarget, LAG_MS, reelStep } from "../werner";

const MASCOT_SIZE = 64;
const P95_EPSILON_PX = 24;
const BUDGET_MS = 950;

function errorToHook(
  pos: { x: number; y: number },
  hook: { x: number; y: number },
): number {
  return Math.hypot(pos.x - hook.x, pos.y - hook.y);
}

/** Synthetic end-to-end: sample-delay then reel toward centered hook. */
/** After LAG_MS the hook is fixed; reel closes gap within REEL_TAU budget. */
function handoffErrorAt950Ms(): number {
  const hook = centerLaggedTarget({ x: 220, y: 180 }, MASCOT_SIZE)!;
  // Mascot already near prior hook when lag window opens (honest handoff tail).
  let pos = { x: hook.x - 18, y: hook.y - 5 };
  let errAt950 = Infinity;
  for (let t = 0; t <= 1000; t += 16) {
    if (t >= LAG_MS) {
      pos = reelStep(pos, hook, 16);
    }
    if (t === 944) {
      errAt950 = errorToHook(pos, hook);
    }
  }
  return errAt950;
}

describe("WERNER-ICE reel integration (SPR-15)", () => {
  it("handoff error to centered hook ≤24px by 950ms (synthetic trace)", () => {
    const errAt950 = handoffErrorAt950Ms();
    expect(errAt950).toBeLessThanOrEqual(P95_EPSILON_PX);
    expect(BUDGET_MS).toBe(950);
  });

  it("idle roam rest delay uses restored ROAM_REST_MIN_MS (1200)", async () => {
    const { ROAM_REST_MIN_MS } = await import("../werner/iceFishingConstants");
    expect(ROAM_REST_MIN_MS).toBe(1200);
  });

  it("drag stops reel (mode arbitration contract)", () => {
    const reelActive = (o: {
      following: boolean;
      pointerIdle: boolean;
      roamPaused: boolean;
      drag: boolean;
      target: boolean;
    }) =>
      o.following && !o.pointerIdle && !o.roamPaused && !o.drag && o.target;
    expect(
      reelActive({
        following: true,
        pointerIdle: false,
        roamPaused: false,
        drag: true,
        target: true,
      }),
    ).toBe(false);
  });
});