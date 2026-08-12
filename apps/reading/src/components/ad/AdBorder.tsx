// The always-on, four-edge "Times-Square" ad border (SPR-07 M2 + M5 + M6).
//
// Mounted ONCE at the shell (AppShell) → it wraps every lens (Read / Research /
// Write / Speak) with ONE code path, no per-lens fork. It SETS the SPR-06
// edge-reservation seam (`--akb-border-inset-*`, tokens.css) to its thickness,
// so AppShell's `[data-akb-shell-frame]` reserves that band as padding and the
// working region shrinks to fit — the border paints ONLY in the reserved inset
// and never overlaps, clips, or shifts the working region (M6 invariant).
//
// TOP/BOTTOM are always present (they never narrow the reading column);
// LEFT/RIGHT appear only on wide viewports, honoring READER_AD_SLOT_POSITIONS_
// DEFAULT (top/bottom) vs the full set (top/bottom/left/right). The viewport
// tier (useViewportTier) drives the crossover.
//
// Non-interference (M6): the border is a sibling of the shell frame with
// `pointer-events:none` on its container; only the creative links re-enable
// pointer events. It carries no tabindex and sits AFTER the working region in
// the (sibling) DOM order conceptually — focus flows to content first. Under
// `prefers-reduced-motion: reduce`, creatives are static (we render no
// animation regardless, so this is honored by construction; the fill cadence
// also stops auto-advancing).

import { useEffect, useMemo, useRef, useState } from "react";

import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import { useViewportTier } from "../../workspace/useViewportTier";
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

// The reserved band thickness per edge. Horizontal rails (top/bottom) are
// shorter than vertical rails are wide because a row of text needs less than a
// stacked column. Tokens-only sizing (Tailwind spacing); no raw hex anywhere.
const RAIL_THICKNESS_PX = { horizontal: 36, vertical: 96 } as const;

/** TOP/BOTTOM always; LEFT/RIGHT only when the viewport is wide enough that
 *  the working column can spare the width (xl/lg, mirroring the docks). */
function activePositions(tier: ReturnType<typeof useViewportTier>): BorderPosition[] {
  const wide = tier === "xl" || tier === "lg";
  return wide ? ["top", "bottom", "left", "right"] : ["top", "bottom"];
}

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
  /** Test/story seam: disable the 1Hz sampler (e.g. static stories). */
  samplingEnabled?: boolean;
}

export function AdBorder({
  lens,
  windowId,
  onTelemetryError,
  fillFetcher = fetchFill,
  samplingEnabled = true,
}: AdBorderProps) {
  const tier = useViewportTier();
  const reduceMotion = usePrefersReducedMotion();
  const positions = useMemo(() => activePositions(tier), [tier]);

  const [fill, setFill] = useState<FillResult>({ fills: [], served: false });

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

  // SET the SPR-06 seam to the border thickness for the active edges; clear
  // (0) for inactive edges so the working region reclaims that width on a
  // wide→narrow crossing. This is the ONLY place the inset is set.
  useEffect(() => {
    const root = document.documentElement;
    const set = (side: BorderPosition, px: number) =>
      root.style.setProperty(`--akb-border-inset-${side}`, `${px}px`);
    const wide = positions.includes("left");
    set("top", RAIL_THICKNESS_PX.horizontal);
    set("bottom", RAIL_THICKNESS_PX.horizontal);
    set("left", wide ? RAIL_THICKNESS_PX.vertical : 0);
    set("right", wide ? RAIL_THICKNESS_PX.vertical : 0);
    return () => {
      // Restore the default-0 contract on unmount so the working region is
      // never left with a phantom inset if the border is removed.
      (["top", "right", "bottom", "left"] as BorderPosition[]).forEach((s) =>
        set(s, 0),
      );
    };
  }, [positions]);

  // Fetch the fills for the active edges. Re-fetches on lens / position change.
  // The route is a deferred seam → degrades to house fill (never blank).
  useEffect(() => {
    const ctl = new AbortController();
    fillFetcher({ windowId, lens, positions, signal: ctl.signal }).then(setFill);
    return () => ctl.abort();
  }, [windowId, lens, positions, fillFetcher]);

  const fillFor = (pos: BorderPosition): SlotFill =>
    fill.fills.find((f) => f.position === pos) ?? {
      fill_decision_id: "local-house",
      slot_id: `local:${pos}`,
      position: pos,
      kind: "house",
      ad: null,
      house: null,
      revenue_usd_cents: 0,
      price_status: "unpriced",
    };

  const h = RAIL_THICKNESS_PX.horizontal;
  const v = RAIL_THICKNESS_PX.vertical;
  const showSides = positions.includes("left");

  // Container: fixed, covers the viewport, pointer-events:none so it NEVER
  // intercepts a click/scroll meant for the working region. Each rail re-enables
  // pointer events on itself only (its creative links are reachable, the
  // working region under it is not occluded — the rails live in the reserved
  // inset band, not over the content). data-akb-ad-border marks the subtree so
  // the M3 sampler excludes the border's own creatives.
  return (
    <div
      data-akb-ad-border
      data-reduced-motion={reduceMotion ? "true" : "false"}
      aria-hidden={false}
      className="fixed inset-0 z-[150] pointer-events-none"
    >
      <Rail
        edge="top"
        style={{ top: 0, left: 0, right: 0, height: h }}
        orientation="horizontal"
        fill={fillFor("top")}
      />
      <Rail
        edge="bottom"
        style={{ bottom: 0, left: 0, right: 0, height: h }}
        orientation="horizontal"
        fill={fillFor("bottom")}
      />
      {showSides && (
        <>
          <Rail
            edge="left"
            style={{ top: h, bottom: h, left: 0, width: v }}
            orientation="vertical"
            fill={fillFor("left")}
          />
          <Rail
            edge="right"
            style={{ top: h, bottom: h, right: 0, width: v }}
            orientation="vertical"
            fill={fillFor("right")}
          />
        </>
      )}
    </div>
  );
}

function Rail({
  edge,
  style,
  orientation,
  fill,
}: {
  edge: BorderPosition;
  style: React.CSSProperties;
  orientation: "horizontal" | "vertical";
  fill: SlotFill;
}) {
  const borderSide =
    edge === "top"
      ? "border-b-edge"
      : edge === "bottom"
        ? "border-t-edge"
        : edge === "left"
          ? "border-r-edge"
          : "border-l-edge";
  return (
    <aside
      // The rail re-enables pointer events on itself (its links are clickable)
      // but it sits in the RESERVED inset band, not over the working region.
      className={`absolute pointer-events-auto bg-ice-1 dark:bg-charcoal-2 border-sun ${borderSide}`}
      style={style}
      aria-label={`Ad border — ${edge}`}
      data-akb-ad-edge={edge}
    >
      <AdCreative fill={fill} orientation={orientation} />
    </aside>
  );
}

export default AdBorder;
