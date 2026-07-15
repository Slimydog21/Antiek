import { WernerFishingLayer } from "../WernerFishingLayer";
import { WernerIceBait } from "../WernerIceBait";
import { registerActivity } from "./registry";
import type { CursorInstrumentProps, StationActivity } from "./types";

/**
 * Ice-fishing — Werner's first (and, this sprint, only) station activity.
 *
 * This is the shipped fixed-station behavior (the merged fixed-station PRs)
 * expressed as a StationActivity, WITHOUT changing what it does. The values equal the
 * constants that were hard-coded in PenguinMascot / WernerIceCursorShell, so
 * the wire-up is behavior-preserving:
 *
 *   - idleClass  "werner-fishing" — the own-hole never-catch gag the mascot's
 *                gag rAF toggles while the pointer is IDLE (was a string literal
 *                in PenguinMascot; it now lives HERE, its one home).
 *   - activeClass null — fishing has no active ambient class; while the pointer
 *                is ACTIVE the rod is at rest and the line-to-cursor is drawn by
 *                the instrument, not by an ambient class.
 *   - instrument the EXISTING WernerIceBait + WernerFishingLayer pairing, reused
 *                verbatim (no duplicated bait/line logic) — the same two layers
 *                WernerIceCursorShell used to hard-wire.
 *
 * It reads the cursor seam (live / pointerIdle / tabHidden) only — never the
 * penguin — which is exactly why the reel could never come back (see types.ts).
 */

/**
 * The ice-fishing cursor-instrument: the bait worm at the cursor + the rod-tip→
 * cursor fishing line. Mounted by WernerIceCursorShell in place of the old
 * hard-wired bait + line pair. Order and props are identical to that original
 * mount (WernerFishingLayer first, then WernerIceBait; both take `disabled`),
 * so nothing observable changes.
 */
function IceFishingInstrument({ disabled = false }: CursorInstrumentProps) {
  return (
    <>
      <WernerFishingLayer disabled={disabled} />
      <WernerIceBait disabled={disabled} />
    </>
  );
}

export const iceFishingActivity: StationActivity = {
  id: "ice-fishing",
  label: "Ice fishing",
  ambient: {
    activeClass: null,
    idleClass: "werner-fishing",
  },
  instrument: {
    render: IceFishingInstrument,
    reads: ["live", "pointerIdle", "tabHidden"],
  },
  unlock: { kind: "default" },
};

// Seed the catalog + mark ice-fishing the default. Importing this module (which
// the activities barrel does) is what makes getDefaultActivity() resolve.
registerActivity(iceFishingActivity, { default: true });
