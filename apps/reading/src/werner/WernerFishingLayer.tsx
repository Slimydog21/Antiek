import { useEffect, useRef } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { catenaryPath, rodTipFromMascotRect } from "./fishingLineGeometry";
import { wernerIceFishingCursor } from "./iceFishingFlags";
import { useMouseFollow } from "./useMouseFollow";

const MASCOT_SIZE = 64;
const MASCOT_TEST_ID = "penguin-mascot";

export interface WernerFishingLayerProps {
  disabled?: boolean;
}

/**
 * Viewport fishing line from rod tip → live bait (SPR-14). pointer-events:none.
 */
export function WernerFishingLayer({ disabled = false }: WernerFishingLayerProps) {
  const pathRef = useRef<SVGPathElement | null>(null);
  const reduceMotion = usePrefersReducedMotion();
  const follow = useMouseFollow({ disabled: disabled || !wernerIceFishingCursor || reduceMotion });

  useEffect(() => {
    if (!wernerIceFishingCursor || disabled || reduceMotion) return;

    let raf = 0;
    const tick = () => {
      const path = pathRef.current;
      const mascot = document.querySelector(
        `button[data-testid="${MASCOT_TEST_ID}"]`,
      ) as HTMLButtonElement | null;
      const reading = follow.read();
      if (!path || !mascot || !reading.live || reading.tabHidden) {
        if (path) path.setAttribute("d", "");
        raf = window.requestAnimationFrame(tick);
        return;
      }
      const rect = mascot.getBoundingClientRect();
      const rod = rodTipFromMascotRect(rect, MASCOT_SIZE);
      const bait = reading.live;
      path.setAttribute("d", catenaryPath(rod, bait));
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [disabled, reduceMotion, follow]);

  if (!wernerIceFishingCursor || disabled || reduceMotion) return null;

  return (
    <svg
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 59,
      }}
    >
      <path
        ref={pathRef}
        fill="none"
        stroke="var(--ink)"
        strokeOpacity={0.4}
        strokeWidth={1}
        strokeLinecap="round"
      />
    </svg>
  );
}

export default WernerFishingLayer;