/**
 * BrainRig.tsx — the floating station mascot, brain edition (SPR-12 M3 surface).
 *
 * Replaces WernerRig's penguin art inside the PenguinMascot station while
 * preserving the rig's LOAD-BEARING contract: the fishing-rod geometry
 * (ROD_BUTT / ROD_TIP shared with fishingLineGeometry.ts) that anchors the
 * ratified cursor-bait line, and the `bend` flex that bows the shaft under
 * line tension. The ratified station interaction model (fixed station, cursor
 * as bait, drag to re-station, single/double-click) is byte-stable — this
 * component only changes WHAT the station shows: the Krea-generated brain
 * (BrainMascot idle) instead of the penguin, with no vector feet/flippers
 * (a brain floats; it does not waddle).
 *
 * Reduced motion: the rod collapses to a straight neutral rest (bend -> 0),
 * same guard as WernerRig.
 */
import type { CSSProperties } from "react";

import BrainMascot from "./BrainMascot";
import { ROD_BUTT, rodSegments } from "../werner/WernerRig";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";

export interface BrainRigProps {
  /** Render size in px (the mascot uses MASCOT_SIZE = 64). */
  size: number;
  /** Screen-reader label for the brain mark. */
  label?: string;
  /** Positioning passthrough for the wrapper. */
  style?: CSSProperties;
  /**
   * Rod flex (perpendicular bow, in 64-viewBox units) under line tension.
   * 0 = a straight rod at rest. Forced to 0 under reduced motion.
   */
  bend?: number;
}

export default function BrainRig({ size, label, style, bend = 0 }: BrainRigProps) {
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
      data-brain-rig=""
    >
      {/* The canonical brain mark (transparent, Krea anchor). */}
      <BrainMascot mood="idle" size={size} label={label} />

      {/* THE ROD — same tapered, optionally-flexing shaft as WernerRig (shared
          builder + shared ROD_BUTT/ROD_TIP contract with fishingLineGeometry).
          aria-hidden — the labelled brain mark above is the accessible name. */}
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
        <g style={{ transformOrigin: `${ROD_BUTT.x}px ${ROD_BUTT.y}px` }}>
          {segments.map((seg, i) => (
            <path
              key={i}
              d={seg.d}
              fill="none"
              stroke="var(--werner-coat)"
              strokeWidth={seg.width}
              strokeLinecap={i === segments.length - 1 ? "round" : "butt"}
            />
          ))}
        </g>
      </svg>
    </span>
  );
}
