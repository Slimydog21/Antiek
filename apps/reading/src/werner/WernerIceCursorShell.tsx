import { useLayoutEffect } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { wernerIceFishingCursor } from "./iceFishingFlags";
import { useStationInstrumentSuspended } from "./stationInstrumentSuspension";
import { useStationActivity } from "./useStationActivity";

/**
 * Shell-level station-instrument policy: mount the route-selected cursor layer
 * and hide the native cursor on pointer devices. Reduced-motion keeps the native
 * cursor and mounts no instrument. This sits outside the route switch so every
 * mode gets exactly one global overlay.
 *
 * Instruments read the pointer seam but cannot write mascot position. The CSS
 * class name remains legacy-compatible with the original ice-fishing rollout.
 */
export function WernerIceCursorShell() {
  const reduceMotion = usePrefersReducedMotion();
  const instrumentSuspended = useStationInstrumentSuspended();
  const activity = useStationActivity();
  // The legacy flag gates ice fishing only. Research lens is a separate
  // activity and must remain available when production disables fishing.
  const enabledByActivity =
    activity.id !== "ice-fishing" || wernerIceFishingCursor;
  const active = enabledByActivity && !reduceMotion && !instrumentSuspended;
  const Instrument = activity.instrument.render;

  // Keep DOM cursor authority in the same pre-paint phase as suspension leases.
  // A passive effect can briefly leave both instruments absent while the root
  // still hides the native cursor.
  useLayoutEffect(() => {
    const root = document.documentElement;
    if (active) root.classList.add("werner-ice-cursor-hidden");
    else root.classList.remove("werner-ice-cursor-hidden");
    return () => root.classList.remove("werner-ice-cursor-hidden");
  }, [active]);

  return <Instrument disabled={!active} />;
}

export default WernerIceCursorShell;
