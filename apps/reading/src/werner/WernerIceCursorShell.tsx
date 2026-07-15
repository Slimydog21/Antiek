import { useEffect } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { getDefaultActivity } from "./activities";
import { wernerIceFishingCursor } from "./iceFishingFlags";

/**
 * Shell-level ice-fishing cursor policy (SPR-13): bait overlay + cursor:none on
 * html when active. Reduced motion disables both.
 *
 * SPR-01: the bait + fishing-line pair is no longer hard-wired here — it is the
 * active (default) activity's cursor-instrument (ice-fishing's instrument mounts
 * the same WernerFishingLayer + WernerIceBait, in the same order, with the same
 * `disabled` prop). With one activity this is behavior-identical; the shell now
 * mounts "whatever the active activity's instrument is" instead of one fixed pair.
 */
export function WernerIceCursorShell() {
  const reduceMotion = usePrefersReducedMotion();
  const active = wernerIceFishingCursor && !reduceMotion;

  const Instrument = getDefaultActivity().instrument.render;

  useEffect(() => {
    const root = document.documentElement;
    if (active) root.classList.add("werner-ice-cursor-hidden");
    else root.classList.remove("werner-ice-cursor-hidden");
    return () => root.classList.remove("werner-ice-cursor-hidden");
  }, [active]);

  return <Instrument disabled={!active} />;
}

export default WernerIceCursorShell;