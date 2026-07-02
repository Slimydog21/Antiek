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
 *
 * Fixed-station model (2026-07-02): the line is shown ONLY while the pointer is
 * ACTIVE — it hangs from Werner's stationary rod tip to the cursor-bait (the
 * cursor IS the bait). When the pointer goes IDLE the line hides, because
 * Werner's own-hole never-catch gag (`werner-fishing`, a line inside the rod's
 * rotating frame) takes over the fishing visual — and the two must never draw
 * at once (one rod, one line). Under the OLD reel this exclusivity came for free
 * (the reel had already pulled Werner ONTO the bait, collapsing this line to
 * zero length); with a fixed rod tip that coincidence never happens, so we gate
 * on `pointerIdle` explicitly. See docs/htmlspec/werner-fixed-station/DESIGN.md.
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
      // Hide the cursor-line when there is no live bait, the tab is hidden, OR
      // the pointer is idle (the own-hole gag owns the fishing visual then).
      if (
        !path ||
        !mascot ||
        !reading.live ||
        reading.tabHidden ||
        reading.pointerIdle
      ) {
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