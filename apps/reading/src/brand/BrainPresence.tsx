/**
 * BrainPresence.tsx — the mascot "in the background" (the operator's brief).
 *
 * A large, very-low-opacity brain drifting slowly behind the app content —
 * ambient life, not chrome. Mounted in AppShell right above the living
 * mountainscape (Scene) and below the content column, so it reads as the
 * product's presence on every route without ever capturing input
 * (pointer-events: none) or competing with the rail/hero marks.
 *
 * It reuses BrainMascot (blink + breathing + pointer tilt all apply — the
 * background brain is alive too), wrapped in a slow CSS float (sanctioned
 * motion home: mascot-brain/brainMascot.css). Under prefers-reduced-motion
 * the float collapses to a static faint mark (the media query in
 * brainMascot.css); the inner BrainMascot already handles its own collapse.
 */
import type { CSSProperties } from "react";

import BrainMascot from "./BrainMascot";
import "./mascot-brain/brainMascot.css";

type Props = {
  /** Render size in px. Default 420 — a large, unmistakable-but-faint mark. */
  size?: number;
  /** Alpha of the presence layer. Default 0.08 — barely-there by design. */
  opacity?: number;
  className?: string;
  style?: CSSProperties;
};

export default function BrainPresence({
  size = 420,
  opacity = 0.08,
  className,
  style,
}: Props) {
  return (
    <div
      aria-hidden="true"
      className={`brain-presence ${className ?? ""}`}
      style={{
        position: "absolute",
        right: "-6%",
        bottom: "-12%",
        width: size,
        height: size,
        opacity,
        pointerEvents: "none",
        zIndex: 1,
        ...style,
      }}
    >
      <BrainMascot mood="idle" size={size} />
    </div>
  );
}
