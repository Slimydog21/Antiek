import { useEffect, useRef } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { zIndex } from "../shell/zScale";
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
      // The line leaves the REAL rod tip: rodTipFromMascotRect defaults localTip
      // to ROD_TIP_LOCAL (the shared SPR-04 contract = WernerRig's ROD_TIP), so
      // this stays one geometry pass per frame — no new tip arg, no new cost.
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
        // z: werner band floor (shell/zScale.ts `werner`) — the fishing-line
        // cursor layer sits just UNDER the mascot itself (`wernerMascot`), over
        // all other shell chrome. Sourced from the z-scale (was a raw 59).
        zIndex: zIndex.werner,
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