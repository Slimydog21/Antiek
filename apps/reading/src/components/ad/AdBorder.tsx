// The shell's one house-ad slot (SPR-07 M2 + M5 + M6; design wave 3).
//
// Mounted ONCE at the shell (AppShell) → it serves every lens (Read / Research /
// Write / Speak) with ONE code path, no per-lens fork. It SETS the SPR-06
// edge-reservation seam (`--akb-border-inset-*`, tokens.css) for its one edge,
// so AppShell's `[data-akb-shell-frame]` reserves that band as padding and the
// working region shrinks to fit — the slot paints ONLY in the reserved inset
// and never overlaps, clips, or shifts the working region (M6 invariant).
//
// ONE labelled slot, in one designated rail along the TOP edge, at every
// width. It used to be a four-edge "Times-Square" border: four "From the
// library" rails wrapping the app, the side rails 96px wide and clipping
// their own text. The design spec (§5) allows one labelled slot. The top edge
// was chosen because it moves nothing below it: the dock and the mascot's
// station keep the viewport's bottom edge whether or not the slot is served.
//
// Non-interference (M6): the slot's container is a fixed layer with
// `pointer-events:none`; only the slot itself re-enables pointer events. It
// carries no tabindex and the working region's content comes first. Under
// `prefers-reduced-motion: reduce` the creative is static (it renders no
// animation regardless; the fill cadence also stops auto-advancing).
//
// Attribution is untouched: the per-second sampler (useFrameAttention) and the
// telemetry emitter run exactly as before, and the slot keeps the
// data-akb-ad-border / data-akb-ad-edge markers the sampler uses to exclude the
// ad's own creative from the working region.

import { useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import AdCreative from "./AdCreative";
import {
  fetchFill,
  type BorderPosition,
  type FillResult,
  type SlotFill,
} from "./adFillClient";
import { FrameTelemetryEmitter, type TelemetryError } from "./frameTelemetryClient";
import type { Lens } from "./frameContract";
import { useFrameAttention } from "./useFrameAttention";

// The slot's reserved band: one row of 14px text plus air.
const SLOT_PX = 32;
// The one edge the slot occupies, at every width. A module constant so the
// fill request's identity is stable across renders.
const POSITIONS: BorderPosition[] = ["top"];
const EDGES: BorderPosition[] = ["top", "right", "bottom", "left"];

export interface AdBorderProps {
  /** The active lens — stamped on every FrameSecond + sent to the fill route
   *  for lens-appropriate creatives. */
  lens: Lens;
  /** A stable id for this window's telemetry batch (trace anchor). */
  windowId: string;
  /** Surfaced telemetry failures (route-absent / version-mismatch). Defaults
   *  to a console.warn so a missing route is visible, never silent (honesty). */
  onTelemetryError?: (err: TelemetryError) => void;
  /** Test/story seam: override the fill fetch. */
  fillFetcher?: typeof fetchFill;
  /** Test/story seam: fill rendered on FIRST paint, before the (async) fetch
   *  resolves. Story screenshots are taken on the first stable frame, so
   *  stories must seed the rails here or they race the fetch and flake. */
  initialFill?: FillResult;
  /** Test/story seam: disable the 1Hz sampler (e.g. static stories). */
  samplingEnabled?: boolean;
}

export function AdBorder({
  lens,
  windowId,
  onTelemetryError,
  fillFetcher = fetchFill,
  initialFill,
  samplingEnabled = true,
}: AdBorderProps) {
  const reduceMotion = usePrefersReducedMotion();
  const positions = POSITIONS;

  const [fill, setFill] = useState<FillResult>(initialFill ?? { fills: [], served: false });

  // The single telemetry emitter for this window. Created once per windowId;
  // the sampler feeds it, lifecycle/interval flushes it (M4).
  const emitterRef = useRef<FrameTelemetryEmitter | null>(null);
  useEffect(() => {
    const emitter = new FrameTelemetryEmitter({
      windowId,
      onError: onTelemetryError ?? ((e) => console.warn("[ad/telemetry]", e)),
    });
    emitter.start();
    emitterRef.current = emitter;
    return () => {
      emitter.stop();
      emitterRef.current = null;
    };
  }, [windowId, onTelemetryError]);

  // Per-second in-frame detection → buffer one FrameSecond. A HOUSE second
  // (no eligible asset in frame) still emits — the samples are simply empty,
  // which the backend weighs as a house second. No fabricated impression.
  useFrameAttention({
    lens,
    windowId,
    enabled: samplingEnabled,
    onSecond: ({ second }) => emitterRef.current?.record(second),
  });

  // SET the SPR-06 seam: the slot's band on its edge, 0 on the other three.
  // This is the ONLY place the inset is set.
  useEffect(() => {
    const root = document.documentElement;
    const set = (side: BorderPosition, px: number) =>
      root.style.setProperty(`--akb-border-inset-${side}`, `${px}px`);
    EDGES.forEach((e) => set(e, positions.includes(e) ? SLOT_PX : 0));
    // Restore the default-0 contract on unmount so the working region is
    // never left with a phantom inset if the slot is removed.
    return () => EDGES.forEach((e) => set(e, 0));
  }, [positions]);

  // Fetch the fills for the active edges. Re-fetches on lens / position change.
  // The route is a deferred seam → degrades to house fill (never blank).
  useEffect(() => {
    const ctl = new AbortController();
    fillFetcher({ windowId, lens, positions, signal: ctl.signal }).then(setFill);
    return () => ctl.abort();
  }, [windowId, lens, positions, fillFetcher]);

  const fill0: SlotFill = fill.fills.find((f) => f.position === "top") ?? {
    fill_decision_id: "local-house",
    slot_id: "local:top",
    position: "top",
    kind: "house",
    ad: null,
    house: null,
    revenue_usd_cents: 0,
    price_status: "unpriced",
  };

  // Container: fixed, covers the viewport, pointer-events:none so it NEVER
  // intercepts a click/scroll meant for the working region. The slot
  // re-enables pointer events on itself only (its link is reachable; it lives
  // in the reserved inset band, not over the content). data-akb-ad-border
  // marks the subtree so the M3 sampler excludes the slot's own creative.
  return (
    <div
      data-akb-ad-border
      data-reduced-motion={reduceMotion ? "true" : "false"}
      className="fixed inset-0 z-[150] pointer-events-none"
    >
      <aside
        className="absolute inset-x-0 top-0 pointer-events-auto bg-inset border-b border-hairline"
        style={{ height: SLOT_PX }}
        aria-label="Sponsored"
        data-akb-ad-edge="top"
      >
        <AdCreative fill={fill0} />
      </aside>
    </div>
  );
}

export default AdBorder;
