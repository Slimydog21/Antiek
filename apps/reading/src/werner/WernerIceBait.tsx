import { useEffect, useRef } from "react";

import { zIndex } from "../shell/zScale";
import { wernerIceFishingCursor } from "./iceFishingFlags";
import { useMouseFollow, type UseMouseFollowOptions } from "./useMouseFollow";
import "./ice-fishing.css";

export interface WernerIceBaitProps {
  /** Mirror reduced-motion freeze from the mascot. */
  disabled?: boolean;
  /** Injectable clock for tests (forwarded to useMouseFollow). */
  now?: UseMouseFollowOptions["now"];
}

/**
 * Live bait cursor overlay (SPR-13). Sits at z-59 under the mascot (z-60).
 * Position is written straight to the DOM each frame — no setState per move.
 */
export function WernerIceBait({ disabled = false, now }: WernerIceBaitProps) {
  const elRef = useRef<HTMLSpanElement | null>(null);
  const follow = useMouseFollow({
    disabled: disabled || !wernerIceFishingCursor,
    now,
  });

  useEffect(() => {
    if (!wernerIceFishingCursor || disabled) return;

    let raf = 0;
    const tick = () => {
      const el = elRef.current;
      if (el) {
        const { live, tabHidden } = follow.read();
        if (!live || tabHidden) {
          el.style.display = "none";
        } else {
          el.style.display = "block";
          el.style.left = `${live.x}px`;
          el.style.top = `${live.y}px`;
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [disabled, follow]);

  if (!wernerIceFishingCursor || disabled) return null;

  return (
    <span
      ref={elRef}
      className="werner-ice-bait"
      aria-hidden="true"
      // z: driven from the single z-scale token (ALC SPR-08 deferral 4a) — the
      // bait sits at the werner band floor, with the fishing-line cursor layer
      // (WernerFishingLayer uses the same `zIndex.werner`), just under the mascot
      // (`wernerMascot`). No CSS literal mirror to desync; the token is the source.
      style={{ zIndex: zIndex.werner }}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
        <ellipse className="werner-ice-bait__worm" cx="5" cy="5.5" rx="3" ry="2" />
        <circle className="werner-ice-bait__hook" cx="7.5" cy="3" r="0.8" />
      </svg>
    </span>
  );
}

export default WernerIceBait;