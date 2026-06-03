import type { CSSProperties } from "react";

import Werner from "../brand/Werner";
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
}

/**
 * The feet + flippers are positioned in a viewBox matched to the Werner art's
 * square so they land on his foot line regardless of `size`. The geometry is
 * deliberately small + at the base — it reads as Werner's own feet peeking
 * out, never as a second creature. Each limb carries the rig class the
 * descendant selectors drive.
 */
export default function WernerRig({ size, label, style }: WernerRigProps) {
  // The feet sit at ~88% down (Werner's foot line); flippers at ~52% (mid-body
  // sides). Coordinates are in a 64-unit viewBox so they scale with `size`.
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
        <g
          className="werner-rig-flipper-r"
          style={{ transformOrigin: "44px 30px" }}
        >
          <ellipse cx="46" cy="36" rx="3" ry="8" fill="var(--werner-coat)" />
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
