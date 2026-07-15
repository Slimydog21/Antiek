export interface Point {
  x: number;
  y: number;
}

/**
 * THE SHARED ROD-TIP CONTRACT (SPR-04).
 * ------------------------------------------------------------------
 * The rig (WernerRig.tsx) and the line layer (WernerFishingLayer.tsx) must
 * agree, to the unit, on WHERE the rod ends — otherwise the catenary leaves a
 * point that is not the rod tip and the rod + line stop reading as one
 * mechanism. That agreement lives HERE, as one exported constant, so a future
 * rod redesign updates the rig and the line in a single read.
 *
 * Coordinates are in the rig's 64-unit viewBox. The matching rig geometry:
 *   - rod butt / grip  = (45, 34)  → WernerRig `ROD_BUTT`, covered by the
 *     authored station body's right flipper (SPR-24).
 *   - rod tip          = (66, 5)   → WernerRig `ROD_TIP`, the end of the shaft.
 * The tip sits PAST the 64-viewBox right/top edge on purpose (the rig SVG is
 * `overflow:visible`), so the rod reads as a long fishing rod rather than a
 * stub that stops at the body. If you move ROD_TIP in WernerRig.tsx, move this
 * value too — they are the same point in two files by necessity, not by
 * accident.
 */
export const ROD_TIP_LOCAL: Point = { x: 66, y: 5 };

/** The rod butt / grip point in the same 64-viewBox space (rig `ROD_BUTT`). */
export const ROD_BUTT_LOCAL: Point = { x: 45, y: 34 };

/**
 * Quadratic catenary-ish line from rod tip to bait (SPR-14).
 * sag = min(40, slack * 0.12) where slack = dist - tautLength.
 *
 * SPR-04 only MOVED where this line starts (the rod tip, via
 * rodTipFromMascotRect's new default localTip); the look + sag formula are
 * unchanged, per the sprint's out-of-scope on restyling the catenary.
 */
export function catenaryPath(
  rod: Point,
  bait: Point,
  tautLength = 24,
): string {
  const dx = bait.x - rod.x;
  const dy = bait.y - rod.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 8) {
    return `M ${rod.x} ${rod.y} L ${bait.x} ${bait.y}`;
  }
  const slack = Math.max(0, dist - tautLength);
  const sag = Math.min(40, slack * 0.12);
  const mx = (rod.x + bait.x) / 2;
  const my = (rod.y + bait.y) / 2 + sag;
  return `M ${rod.x} ${rod.y} Q ${mx} ${my} ${bait.x} ${bait.y}`;
}

/**
 * Rod tip in screen space from the mascot bounding box (64px viewBox scale).
 *
 * The default `localTip` is the SHARED rod-tip contract `ROD_TIP_LOCAL` — the
 * real end of the shaft drawn in WernerRig.tsx. (Pre-SPR-04 this defaulted to
 * the old shoulder stub {x:50,y:22}; the line then left a point Werner was not
 * holding the rod at.) Screen space = viewport-left + tipLocal * (size/64).
 */
export function rodTipFromMascotRect(
  rect: DOMRect,
  mascotSize: number,
  localTip: Point = ROD_TIP_LOCAL,
): Point {
  const scale = mascotSize / 64;
  return {
    x: rect.left + localTip.x * scale,
    y: rect.top + localTip.y * scale,
  };
}

/**
 * Bend (perpendicular bow, in viewBox units) of a rod under line tension.
 *
 * TENSION MODEL — the rod bows toward the load. "Tension" is the line length
 * out: the farther the bait, the more line is hauling on the tip, the more the
 * shaft flexes. We map distance → bend with a saturating curve so it reads like
 * a fishing rod (a far cast bends the tip noticeably; a near bait barely bows
 * it) without ever folding the rod over on itself.
 *
 *   bend(d) = MAX_BEND * d / (d + HALF_BEND_DIST)
 *
 * Rationale for the two constants (both in 64-viewBox units, the rig's space):
 *   - HALF_BEND_DIST = 60: the distance at which the rod reaches HALF its max
 *     bend. ~60 units ≈ one mascot-width of line out — a mid-range cast — so the
 *     curve is in its sensitive band over the distances a cursor-chased bait
 *     actually produces, not flat-lined.
 *   - MAX_BEND = 6: the asymptotic bow. The shaft is ~36 units long (butt→tip);
 *     a 6-unit perpendicular bow is a clear, believable flex (~1/6 of length)
 *     that still reads as a rod under load, never a hoop. The saturation means
 *     even an off-screen bait can't bend it past this.
 *
 * Monotone non-decreasing in distance by construction (d/(d+k) rises with d for
 * k>0) — the deterministic test sweeps distance and asserts curvature only ever
 * grows. At rest / under reduced motion the caller passes bend 0 (straight).
 */
export const ROD_MAX_BEND = 6;
export const ROD_HALF_BEND_DIST = 60;

export function rodBend(tipToBaitDistance: number): number {
  const d = Math.max(0, tipToBaitDistance);
  return (ROD_MAX_BEND * d) / (d + ROD_HALF_BEND_DIST);
}

/** Total rod length (butt→tip) in viewBox units — the contract the rig draws. */
export function rodLength(): number {
  return Math.hypot(
    ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x,
    ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y,
  );
}
