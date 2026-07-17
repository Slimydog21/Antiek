import { useEffect, useRef } from "react";

import { wernerIceFishingCursor } from "./iceFishingFlags";
import {
  useMouseFollow,
  type FollowReading,
  type UseMouseFollowOptions,
} from "./useMouseFollow";
import "./ice-fishing.css";

export interface WernerIceBaitProps {
  /** Mirror reduced-motion freeze from the mascot. */
  disabled?: boolean;
  /** Injectable clock for tests (forwarded to useMouseFollow). */
  now?: UseMouseFollowOptions["now"];
}

/**
 * Pure instrument densify: the cursor IS the bait (fixed-station model — not a
 * chase pet). Hide when there is no live pointer or the tab is hidden; otherwise
 * pin chrome to the live client point. Unit-tested without RAF/DOM thrash.
 */
export function baitChromeFromFollow(
  reading: Pick<FollowReading, "live" | "tabHidden">,
): { display: "none" } | { display: "block"; left: string; top: string } {
  if (!reading.live || reading.tabHidden) return { display: "none" };
  return {
    display: "block",
    left: `${reading.live.x}px`,
    top: `${reading.live.y}px`,
  };
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
        const chrome = baitChromeFromFollow(follow.read());
        el.style.display = chrome.display;
        if (chrome.display === "block") {
          el.style.left = chrome.left;
          el.style.top = chrome.top;
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [disabled, follow]);

  if (!wernerIceFishingCursor || disabled) return null;

  return (
    <span ref={elRef} className="werner-ice-bait" aria-hidden="true">
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
        <ellipse className="werner-ice-bait__worm" cx="5" cy="5.5" rx="3" ry="2" />
        <circle className="werner-ice-bait__hook" cx="7.5" cy="3" r="0.8" />
      </svg>
    </span>
  );
}

export default WernerIceBait;