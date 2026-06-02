import { useEffect } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { wernerIceFishingCursor } from "./iceFishingFlags";
import { WernerIceBait } from "./WernerIceBait";
import { WernerFishingLayer } from "./WernerFishingLayer";

/**
 * Shell-level ice-fishing cursor policy (SPR-13): bait overlay + cursor:none on
 * html when active. Reduced motion disables both.
 */
export function WernerIceCursorShell() {
  const reduceMotion = usePrefersReducedMotion();
  const active = wernerIceFishingCursor && !reduceMotion;

  useEffect(() => {
    const root = document.documentElement;
    if (active) root.classList.add("werner-ice-cursor-hidden");
    else root.classList.remove("werner-ice-cursor-hidden");
    return () => root.classList.remove("werner-ice-cursor-hidden");
  }, [active]);

  return (
    <>
      <WernerFishingLayer disabled={!active} />
      <WernerIceBait disabled={!active} />
    </>
  );
}

export default WernerIceCursorShell;