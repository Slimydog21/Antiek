import type { CSSProperties } from "react";

import WernerAuthoredPose from "../brand/werner/WernerAuthoredPose";
import { ROD_BUTT_LOCAL, ROD_TIP_LOCAL } from "./fishingLineGeometry";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import "./waddle.css";

/**
 * WernerRig (SPR-06 M1 → SPR-24) — the labelled station rig.
 *
 * LAYER MODEL (SPR-24 — hard to vary):
 *   1. Code rod SVG — the tapered, optionally-flexing fishing rod. Rendered
 *      BEHIND the authored body so the shaft appears to emerge from behind
 *      the penguin (the authored flipper covers the butt). overflow:visible
 *      so the tip extends past the 64-viewBox edge.
 *   2. Authored body (`WernerAuthoredPose stationFishing`) — an exact,
 *      deterministically reframed crop of canonical Werner. It has complete
 *      attached feet and flippers, but no rod, line, hook, fish, snow, shadow,
 *      background, text, or motion marks. Decorative (aria-hidden); the outer
 *      fixed-size wrapper owns the accessible name.
 *   3. Code line/fish SVG — the idle fishing loop marks (line + fish), hidden
 *      at rest (opacity 0), revealed only by the `.werner-fishing` keyframes.
 *      Rendered AFTER (in front of) the authored body so they are visible
 *      foreground marks.
 *
 * The vector feet + flippers that previously sat in the SVG overlay are
 * REMOVED (SPR-24). Their geometry is now baked into the authored body PNG
 * (the body contains complete attached feet and flippers). Locomotion is one
 * whole-body silhouette waddle (`werner-step`),
 * not alternating articulated limbs.
 *
 * THE ROD — geometry shared with the line layer (the SPR-04 contract).
 * ROD_BUTT_LOCAL / ROD_TIP_LOCAL live in fishingLineGeometry.ts so the rig
 * and the catenary agree, to the unit, on where the rod begins and ends.
 * Butt = (45,34), tip = (66,5). The tip sits past the 64-viewBox edge
 * (overflow:visible) so the rod reads as a long fishing rod.
 *
 * IT OWNS NO MOTION SOURCE. The rod bend is driven by the `bend` prop;
 * the fishing loop (rod swing + line + fish) is driven by the `.werner-fishing`
 * CSS class on an ancestor (the bob span in PenguinMascot.tsx). The whole-body
 * waddle (`werner-step`) is also driven by an ancestor class.
 *
 * REDUCED MOTION: the rod flex collapses to 0 (JS guard below) and the CSS
 * reduced-motion guard in waddle.css neutralises all transforms/animations.
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
   * 0 = a straight rod at rest. A future tension wiring feeds
   * `rodBend(tipToBaitDistance)` here; today the rod rests straight.
   * Forced to 0 under reduced motion (a static neutral rod, no flex).
   */
  bend?: number;
}

/**
 * THE ROD — geometry shared with the line layer (the SPR-04 contract).
 * ROD_BUTT_LOCAL / ROD_TIP_LOCAL live in fishingLineGeometry.ts so the rig and
 * the catenary agree, to the unit, on where the rod begins and ends. The grip
 * is the butt: the authored body's right flipper covers it and the rod `<g>`'s
 * transform-origin sits there, so a future cast pivots the whole rod from the
 * hand, not the body centre.
 */
const ROD_BUTT = ROD_BUTT_LOCAL; // (45,34) — covered by the authored right flipper
const ROD_TIP = ROD_TIP_LOCAL; // (66,5) — end of the shaft (past the viewBox; overflow:visible)

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
function rodSegments(
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

export default function WernerRig({ size, label, style, bend = 0 }: WernerRigProps) {
  // REDUCED MOTION (M5): the rod holds a STRAIGHT neutral rest pose — the flex
  // collapses to 0 — so reduced motion gets a static rod, never a frozen mid-
  // bend. The CSS reduced-motion guard in waddle.css neutralises all limb/rod/
  // fish/line transforms and animations.
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
      role="img"
      aria-label={label ?? "Werner idle"}
    >
      {/* Layer 1: Code rod SVG — BEHIND the authored body. The shaft emerges
          from behind the penguin; the authored flipper covers the butt, so the
          visible rod reads as gripped in the hand. overflow:visible so the tip
          extends past the 64-viewBox edge. aria-hidden — the Werner mark is the
          accessible name; the rod is decorative. */}
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
        {/* THE ROD (SPR-04) — a long, tapered, optionally-flexing fishing rod.
            Structured as its own <g> with transform-origin AT THE GRIP
            (ROD_BUTT 45,34), so a future cast can rotate the whole rod from the
            hand without re-deriving the rig. Butt = ROD_BUTT (45,34), tip =
            ROD_TIP (66,5) — the SHARED contract with fishingLineGeometry.ts.
            Token-coloured via --werner-rod (no raw hex). */}
        <g
          data-werner-rod=""
          aria-hidden="true"
          style={{ transformOrigin: `${ROD_BUTT.x}px ${ROD_BUTT.y}px` }}
        >
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
      </svg>

      {/* Layer 2: Canonical-derived station body (SPR-24) — an exact,
          deterministically reframed crop with complete attached feet and
          flippers. It contains no rod, line, hook, fish, snow, shadow,
          background, text, or motion marks. Decorative (aria-hidden); the
          fixed-size wrapper above owns the accessible name. */}
      <WernerAuthoredPose
        pose="stationFishing"
        size={size}
        className="werner-station-body"
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          pointerEvents: "none",
        }}
      />

      {/* Layer 3: Code line/fish SVG — FOREGROUND. The idle fishing loop marks
          (line + fish), hidden at rest (opacity 0), revealed only by the
          .werner-fishing keyframes while the gag runs. Rendered AFTER (in front
          of) the authored body so they are visible foreground marks. */}
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
        {/* ── SPR-05: THE ENDLESS-FISHING-LOOP MARKS (the idle gag). ──────────
            The idle line + Werner's OWN little fish. BOTH are inert at rest:
            they only animate when an ancestor carries the `werner-fishing`
            class (added by PenguinMascot ONLY while the loop owns Werner —
            ambient idle + pointer idle). The keyframe cartoon (waddle.css) swings
            the rod <g> in the back SVG, drops/snaps THIS line, and drifts/escapes
            THIS fish through cast→wait→bob→nibble→yank→miss→slump→reset, forever,
            never landing the fish.

            ONE LINE invariant: this idle line is SEPARATE from the
            WernerFishingLayer viewport line — that one draws rod-tip → LIVE
            CURSOR only during pointer-active, which is exactly when the loop is
            OFF, so the two never draw at once. */}

        {/* The idle line: hangs DOWN from the real rod tip (ROD_TIP 66,5). It
            scales from the tip (transform-origin) so the cast extends it and
            the miss snaps it up empty. Token --werner-rod stroke (same line
            material as the rod). HIDDEN at rest by default (opacity 0) — the
            element opacity is animated up ONLY by the .werner-fishing keyframes
            while the loop runs. */}
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
            .werner-fishing keyframes animate it up ONLY while the loop runs. */}
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
      </svg>
    </span>
  );
}
