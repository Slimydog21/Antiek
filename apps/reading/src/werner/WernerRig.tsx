import type { CSSProperties } from "react";

import Werner from "../brand/Werner";
import { ROD_BUTT_LOCAL, ROD_TIP_LOCAL } from "./fishingLineGeometry";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import "./waddle.css";

/**
 * WernerRig (SPR-06 M1) — the VECTOR WALK-CYCLE rig.
 *
 * THE PROBLEM IT FIXES (the "sliding sprite" complaint)
 * -----------------------------------------------------
 * The v1 mascot eased its `left/top` across the viewport while the penguin ART
 * stayed a single static frame — so it read as a dragged sticker, not a walking
 * bird. This component overlays two VECTOR FEET + two FLIPPER marks on the
 * canonical Werner art and animates THOSE limbs, so a stroll reads as real
 * footwork: alternating steps + counter-swinging flippers, a two-beat waddle.
 *
 * IT OWNS NO MOTION SOURCE (the load-bearing constraint — ONE penguin, ONE
 * roamTimer). The limbs are driven ENTIRELY by the EXISTING walk signal: the
 * mascot's roam (PenguinMascot.tsx) already toggles the `werner-waddle` class
 * onto the bob span for the duration of every stroll leg, and `werner-step` for
 * a directed waddle-to-button. The foot/flipper keyframes (waddle.css) are
 * DESCENDANT-SELECTED off those two classes, so the rig animates exactly when
 * Werner is mid-stroll and rests otherwise — with NO new timer, NO rAF, NO
 * second `pos` ref. The rig is a pure RENDERING change: the ratified interaction
 * model (single/double-click, drag-clamp, idle roam) is byte-stable, because
 * the rig consumes the signal that model already produces.
 *
 * ON-FORM + TRANSPARENT: the limbs sit at Werner's base, scaled to his foot
 * line, and use the brand --werner-foot / --werner-coat tokens (no hex
 * literals → token-lint clean). The Werner art itself is the alpha-cut
 * transparent variant (SPR-06 M2), so there is no white box behind the rig.
 *
 * REDUCED MOTION: the limb keyframes collapse to a still neutral frame under
 * `prefers-reduced-motion: reduce` (the guard at the foot of waddle.css), and —
 * since the roam effect early-returns and never adds the walk classes under
 * reduced motion — the descendant selectors never match either. Two lines of
 * defence, same as the rest of the Werner motion system.
 */

export interface WernerRigProps {
  /** Render size in px (the mascot uses MASCOT_SIZE = 64). */
  size: number;
  /** Screen-reader label for the penguin mark. */
  label?: string;
  /** Positioning passthrough for the wrapper. */
  style?: CSSProperties;
  /**
   * Rod flex (perpendicular bow, in 64-viewBox units) under line tension.
   * 0 = a straight rod at rest. A future tension wiring (or SPR-05's cast)
   * feeds `rodBend(tipToBaitDistance)` here; today the rod rests straight.
   * Forced to 0 under reduced motion (a static neutral rod, no flex).
   */
  bend?: number;
}

/**
 * THE ROD — geometry shared with the line layer (the SPR-04 contract).
 * ROD_BUTT_LOCAL / ROD_TIP_LOCAL live in fishingLineGeometry.ts so the rig and
 * the catenary agree, to the unit, on where the rod begins and ends. The grip
 * is the butt: the right flipper curls around it and the rod `<g>`'s
 * transform-origin sits there, so a future cast (SPR-05) pivots the whole rod
 * from the hand, not the body centre.
 */
export const ROD_BUTT = ROD_BUTT_LOCAL; // (45,34) — curled into werner-rig-flipper-r
export const ROD_TIP = ROD_TIP_LOCAL; // (66,5) — end of the shaft (past the viewBox; overflow:visible)

/** Stroke width butt→tip — the rod TAPERS so it reads as a rod, not a stick. */
const ROD_BUTT_WIDTH = 2.6;
const ROD_TIP_WIDTH = 0.7;
/** How many stroked segments to step the taper + bend across (more = smoother). */
const ROD_SEGMENTS = 6;

/**
 * Build the rod as a sequence of stroked segments along a quadratic Bézier
 * (butt → control → tip). SVG strokes cannot taper natively, so we step the
 * width down across the segments — wide at the butt, thin at the tip — which is
 * what makes it read as a rod. The control point is offset PERPENDICULAR to the
 * straight butt→tip axis by `bend` viewBox units, so `bend=0` is a dead-straight
 * rod and a positive `bend` bows the shaft toward the load (the line side).
 */
export function rodSegments(
  bend: number,
): Array<{ d: string; width: number }> {
  const ax = ROD_TIP.x - ROD_BUTT.x;
  const ay = ROD_TIP.y - ROD_BUTT.y;
  const len = Math.hypot(ax, ay) || 1;
  // Unit perpendicular to the rod axis (rotate the axis +90°). The rod runs
  // up-and-right; this perpendicular points up-and-left, so a positive bend
  // bows the shaft toward where the line hangs (visually "loaded").
  const px = -ay / len;
  const py = ax / len;
  // Quadratic control point: midpoint of the chord, pushed out by `bend`.
  const cx = (ROD_BUTT.x + ROD_TIP.x) / 2 + px * bend;
  const cy = (ROD_BUTT.y + ROD_TIP.y) / 2 + py * bend;

  const bez = (t: number) => {
    const mt = 1 - t;
    return {
      x: mt * mt * ROD_BUTT.x + 2 * mt * t * cx + t * t * ROD_TIP.x,
      y: mt * mt * ROD_BUTT.y + 2 * mt * t * cy + t * t * ROD_TIP.y,
    };
  };

  const segs: Array<{ d: string; width: number }> = [];
  for (let i = 0; i < ROD_SEGMENTS; i++) {
    const t0 = i / ROD_SEGMENTS;
    const t1 = (i + 1) / ROD_SEGMENTS;
    const p0 = bez(t0);
    const p1 = bez(t1);
    // Taper: width at this segment's midpoint, lerped butt→tip.
    const tm = (t0 + t1) / 2;
    const width = ROD_BUTT_WIDTH + (ROD_TIP_WIDTH - ROD_BUTT_WIDTH) * tm;
    segs.push({
      d: `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} L ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`,
      width,
    });
  }
  return segs;
}

/**
 * The feet + flippers are positioned in a viewBox matched to the Werner art's
 * square so they land on his foot line regardless of `size`. The geometry is
 * deliberately small + at the base — it reads as Werner's own feet peeking
 * out, never as a second creature. Each limb carries the rig class the
 * descendant selectors drive.
 */
export default function WernerRig({ size, label, style, bend = 0 }: WernerRigProps) {
  // The feet sit at ~88% down (Werner's foot line); flippers at ~52% (mid-body
  // sides). Coordinates are in a 64-unit viewBox so they scale with `size`.
  //
  // REDUCED MOTION (M5): the rod holds a STRAIGHT neutral rest pose — the flex
  // collapses to 0 — so reduced motion gets a static rod, never a frozen mid-
  // bend. (The limb walk-cycle's reduced-motion guard already lives in
  // waddle.css + the roam's JS early-return; this is the rod's matching JS
  // guard, paired with the new `@media` rod block in waddle.css.)
  const reduceMotion = usePrefersReducedMotion();
  const restBend = reduceMotion ? 0 : bend;
  const segments = rodSegments(restBend);
  return (
    <span
      className="inline-block align-middle"
      style={{
        position: "relative",
        display: "block",
        width: size,
        height: size,
        ...style,
      }}
      data-werner-rig=""
    >
      {/* The canonical Werner mark (transparent, SPR-06 M2). The base body +
          breathing sway; the rig limbs ride over it. */}
      <Werner mood="idle" size={size} label={label} />

      {/* The vector limbs overlay. aria-hidden — the labelled Werner mark
          above is the accessible name; these are decorative footwork. */}
      <svg
        viewBox="0 0 64 64"
        width={size}
        height={size}
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          pointerEvents: "none",
          overflow: "visible",
        }}
      >
        {/* Flippers — thin coat-coloured paddles at the mid-body sides, behind
            the feet in stacking so they read as arms swinging beside him. */}
        <g
          className="werner-rig-flipper-l"
          style={{ transformOrigin: "20px 30px" }}
        >
          <ellipse cx="18" cy="36" rx="3" ry="8" fill="var(--werner-coat)" />
        </g>
        {/* RIGHT FLIPPER — reshaped into a GRIP (SPR-04 M1). Instead of a flat
            paddle resting at the side, it curls UP to the rod butt at
            ROD_BUTT (45,34) and wraps around it, so the hand reads as holding
            the rod. The paddle body still sits at the mid-body side; a short
            curl reaches over the butt so grip + rod overlap with no gap. The
            transform-origin is the grip, matching the rod's pivot, so a future
            cast swings the flipper-and-rod together from the hand. */}
        <g
          className="werner-rig-flipper-r"
          style={{ transformOrigin: `${ROD_BUTT.x}px ${ROD_BUTT.y}px` }}
        >
          {/* Forearm/paddle, angled up toward the grip. */}
          <path
            d="M44 41 Q41 37 43 33 Q44.5 31 47 32 Q49 33 48 36 Q47 40 44 41 Z"
            fill="var(--werner-coat)"
          />
          {/* The curl that wraps OVER the rod butt at (45,34) — closes the hand
              around the shaft so there is no gap between flipper and rod. */}
          <ellipse cx="45" cy="34" rx="3.2" ry="2.4" fill="var(--werner-coat)" />
        </g>

        {/* THE ROD (SPR-04) — a long, tapered, optionally-flexing fishing rod
            gripped in the right flipper. Structured as its own <g> with
            transform-origin AT THE GRIP (ROD_BUTT 45,34), so SPR-05's cast can
            rotate the whole rod from the hand without re-deriving the rig.
            Butt = ROD_BUTT (45,34), tip = ROD_TIP (66,5) — the SHARED contract
            with fishingLineGeometry.ts (the catenary leaves ROD_TIP). The tip
            sits PAST the 64-viewBox edge; the rig SVG is overflow:visible so the
            rod reads long instead of clipping at the body. Token-coloured via
            --werner-rod (no raw hex). NOTE (standalone build): SPR-01's typed
            RigPart/pose-machine is deferred, so this is a clean structured <g>
            with a grip transform-origin (same visible outcome, liftable later)
            rather than a registered RigPart. */}
        <g
          data-werner-rod=""
          aria-hidden="true"
          style={{ transformOrigin: `${ROD_BUTT.x}px ${ROD_BUTT.y}px` }}
        >
          {/* Butt cap at the grip — a small node that reads as the rod handle
              seated in the flipper (overlaps the grip curl, no gap). */}
          <ellipse cx="45" cy="34" rx="1.8" ry="1.8" fill="var(--werner-rod)" />
          {/* The tapered, (optionally) flexing shaft butt→tip. Stepped widths
              give the taper SVG strokes can't do natively; bend bows the shaft
              toward the load (0 = straight rest / reduced motion). */}
          {segments.map((seg, i) => (
            <path
              key={i}
              d={seg.d}
              stroke="var(--werner-rod)"
              strokeWidth={seg.width}
              strokeLinecap="round"
              fill="none"
            />
          ))}
        </g>

        {/* ── SPR-05: THE ENDLESS-FISHING-LOOP MARKS (the idle gag). ──────────
            The idle line + Werner's OWN little fish. BOTH are inert at rest:
            they only animate when an ancestor carries the `werner-fishing`
            class (added by PenguinMascot ONLY while the loop owns Werner —
            ambient idle + pointer idle; the SPR-03 reel owns him otherwise, one
            owner at a time). The keyframe cartoon (waddle.css) swings the rod
            <g> above, drops/snaps THIS line, and drifts/escapes THIS fish
            through cast→wait→bob→nibble→yank→miss→slump→reset, forever, never
            landing the fish.

            ONE LINE invariant: this idle line is SEPARATE from the
            WernerFishingLayer viewport line — that one draws rod-tip → LIVE
            CURSOR only during reel-follow (pointer moving), which is exactly
            when the loop is OFF, so the two never draw at once. This is the
            "documented idle variant" the sprint allows: a short, rig-local line
            for the self-contained gag, not a second concurrent cursor line. */}

        {/* The idle line: hangs DOWN from the real rod tip (ROD_TIP 66,5). It
            scales from the tip (transform-origin) so the cast extends it and
            the miss snaps it up empty. Token --werner-rod stroke (same line
            material as the rod). HIDDEN at rest by default (opacity 0) — the
            element opacity is animated up ONLY by the .werner-fishing keyframes
            while the loop runs, so a resting / flag-off / reduced-motion Werner
            shows no stray dangling line (the gag's line, not a second cursor
            line). strokeOpacity tunes the line's weight while it IS shown. */}
        <line
          className="werner-rig-line"
          x1={ROD_TIP.x}
          y1={ROD_TIP.y}
          x2={ROD_TIP.x - 2}
          y2={ROD_TIP.y + 22}
          stroke="var(--werner-rod)"
          strokeWidth={0.6}
          strokeOpacity={0.55}
          strokeLinecap="round"
          opacity={0}
          style={{ transformOrigin: `${ROD_TIP.x}px ${ROD_TIP.y}px` }}
        />

        {/* Werner's OWN fish — a tiny token-coloured (--werner-fish, brand
            aurora teal) mark below the line end. NEVER the cursor, NEVER the
            ice-bait worm (the red --ice-fishing bait). A simple body + tail
            triangle; it drifts up to the hook on the near-catch then darts away
            on the miss. HIDDEN at rest by default (opacity 0 on the group) — the
            .werner-fishing keyframes animate it up ONLY while the loop runs, so a
            resting / flag-off / reduced-motion Werner shows no stray teal fish
            (no white box, no dangling mark). */}
        <g
          className="werner-rig-fish"
          opacity={0}
          style={{ transformOrigin: `${ROD_TIP.x - 2}px ${ROD_TIP.y + 24}px` }}
        >
          {/* Body — a small lozenge. */}
          <ellipse
            cx={ROD_TIP.x - 2}
            cy={ROD_TIP.y + 24}
            rx={2.6}
            ry={1.5}
            fill="var(--werner-fish)"
          />
          {/* Tail — a little fan behind the body. */}
          <path
            d={`M ${ROD_TIP.x + 0.4} ${ROD_TIP.y + 24} l 2 -1.4 l 0 2.8 Z`}
            fill="var(--werner-fish)"
          />
        </g>

        {/* Feet — two sun-coloured webbed feet on the foot line. These are the
            primary walk-cycle signal: they lift in alternation as he strolls. */}
        <g
          className="werner-rig-foot-l"
          style={{ transformOrigin: "26px 56px" }}
        >
          <path
            d="M22 56 L30 56 L28 62 L24 62 Z"
            fill="var(--werner-foot)"
          />
        </g>
        <g
          className="werner-rig-foot-r"
          style={{ transformOrigin: "38px 56px" }}
        >
          <path
            d="M34 56 L42 56 L40 62 L36 62 Z"
            fill="var(--werner-foot)"
          />
        </g>
      </svg>
    </span>
  );
}
