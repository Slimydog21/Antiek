import { useEffect, useRef } from "react";

import AdBorder from "../../modes/Reading/AdBorder";
import type { AdFillView } from "../../modes/Reading/AdBorder";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";

/**
 * WindowAdBorder — the "Times-Square" frame around a WorkspaceWindow (SPR-09 M3).
 *
 * It reuses the Read-mode <AdBorder> (the AdFillView primitive: kind "ad" |
 * "house", with a fully-designed house fallback that is NEVER blank). A window
 * is bordered on all four edges so it reads like a lit marquee around the
 * floating page.
 *
 * Contract (inherited from the ad primitives, unchanged here):
 *   - FILLS COME FROM THE PARENT. This component never fetches. The window
 *     host (or, in production, the §9 fill route via the shell) supplies a
 *     per-edge fill; with no buyer the edge is `kind:"house"` and the house
 *     slot renders a useful recommendation — never blank filler.
 *   - SUPPRESSION is honored: an edge marked suppressed (e.g. the §5.5
 *     voice-discipline test failed for the hosted context) does NOT render a
 *     paid ad; it degrades to the house fill (still never blank), and the
 *     suppression is reported upward via onSuppressed.
 *   - onImpression fires once per served paid-ad edge per fill-set, so the
 *     anti-gaming layer can score it (no fabricated house impressions).
 *
 * Motion: there is no animation here by construction (the rails are static),
 * so prefers-reduced-motion is honored trivially; we still stamp
 * data-reduced-motion for parity with the shell's always-on border and to
 * assert the contract in tests.
 */

export type WindowAdEdge = "top" | "bottom" | "left" | "right";

export interface WindowAdBorderProps {
  /** Stable id of the host window — used to namespace per-edge slot ids and
   *  to dedupe impressions per (window, edge). */
  windowId: string;
  /**
   * Parent-supplied per-edge fills. A missing edge falls back to a neutral
   * house fill (never blank). Fills are NEVER fetched here.
   */
  fills?: Partial<Record<WindowAdEdge, AdFillView>>;
  /**
   * Per-edge suppression predicate result. A suppressed edge degrades any
   * paid ad to the house fill and reports via onSuppressed.
   */
  suppressed?: Partial<Record<WindowAdEdge, boolean>>;
  /** Fired once per served paid-ad edge (advertiserName as the campaign key). */
  onImpression?: (slotId: string, advertiserName: string) => void;
  /** Fired when a paid ad was suppressed for an edge (reason for audit). */
  onSuppressed?: (slotId: string, reason: string) => void;
  /** House-slot "open this recommendation" passthrough. */
  onOpenHouse?: (documentId: string) => void;
}

const EDGES: WindowAdEdge[] = ["top", "bottom", "left", "right"];

/** Neutral house fill — the never-blank default for an edge with no buyer. */
const HOUSE_FALLBACK: AdFillView = { kind: "house", house: null };

/** Resolve the effective fill for an edge, honoring suppression. A suppressed
 *  paid ad degrades to house; a house fill is unaffected. */
function effectiveFill(
  raw: AdFillView | undefined,
  isSuppressed: boolean,
): { fill: AdFillView; suppressedAd: AdFillView["ad"] | null } {
  const fill = raw ?? HOUSE_FALLBACK;
  if (fill.kind === "ad" && fill.ad && isSuppressed) {
    return { fill: HOUSE_FALLBACK, suppressedAd: fill.ad };
  }
  return { fill, suppressedAd: null };
}

export function WindowAdBorder({
  windowId,
  fills,
  suppressed,
  onImpression,
  onSuppressed,
  onOpenHouse,
}: WindowAdBorderProps) {
  const reduceMotion = usePrefersReducedMotion();

  // Resolve all four edges up front (pure) so the impression/suppression
  // effect and the render agree on the same fills.
  const resolved = EDGES.map((edge) => {
    const slotId = `win:${windowId}:${edge}`;
    const { fill, suppressedAd } = effectiveFill(
      fills?.[edge],
      Boolean(suppressed?.[edge]),
    );
    return { edge, slotId, fill, suppressedAd };
  });

  // Fire impressions/suppressions once per fill-set. We key on the serialized
  // fills so re-renders that don't change the fills don't double-count.
  const reportedKeyRef = useRef<string>("");
  useEffect(() => {
    const key = JSON.stringify(resolved.map((r) => [r.slotId, r.fill, r.suppressedAd]));
    if (key === reportedKeyRef.current) return;
    reportedKeyRef.current = key;
    for (const r of resolved) {
      if (r.suppressedAd) {
        onSuppressed?.(
          r.slotId,
          `§5.5 voice-discipline suppression on window edge ${r.edge}`,
        );
      } else if (r.fill.kind === "ad" && r.fill.ad) {
        onImpression?.(r.slotId, r.fill.ad.advertiserName);
      }
    }
    // resolved is recomputed each render; the key guard above makes this a
    // no-op unless the fills actually changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  });

  const byEdge = (edge: WindowAdEdge) => resolved.find((r) => r.edge === edge)!;

  // The frame is a pointer-events:none overlay sitting in the window's reserved
  // border band; each rail re-enables pointer events on itself only, so the
  // hosted page underneath is never occluded by a dead click target.
  return (
    <div
      data-window-ad-border={windowId}
      data-reduced-motion={reduceMotion ? "true" : "false"}
      aria-label="Window ad border"
      className="pointer-events-none absolute inset-0"
    >
      <div className="pointer-events-auto absolute top-0 left-0 right-0">
        <AdBorder
          slotId={byEdge("top").slotId}
          position="top"
          fill={byEdge("top").fill}
          onOpenHouse={onOpenHouse}
        />
      </div>
      <div className="pointer-events-auto absolute left-0 right-0 bottom-0">
        <AdBorder
          slotId={byEdge("bottom").slotId}
          position="bottom"
          fill={byEdge("bottom").fill}
          onOpenHouse={onOpenHouse}
        />
      </div>
      {/* Left + right rails complete the Times-Square frame on wide windows.
          They reuse the same primitive; AdBorder renders top/bottom semantics
          but the house/ad/never-blank contract is identical per edge. */}
      <div className="pointer-events-auto absolute top-[44px] bottom-[44px] left-0 w-[56px] hidden lg:flex items-stretch">
        <div className="w-full [writing-mode:vertical-rl]">
          <AdBorder
            slotId={byEdge("left").slotId}
            position="top"
            fill={byEdge("left").fill}
            onOpenHouse={onOpenHouse}
          />
        </div>
      </div>
      <div className="pointer-events-auto absolute top-[44px] bottom-[44px] right-0 w-[56px] hidden lg:flex items-stretch">
        <div className="w-full [writing-mode:vertical-rl]">
          <AdBorder
            slotId={byEdge("right").slotId}
            position="bottom"
            fill={byEdge("right").fill}
            onOpenHouse={onOpenHouse}
          />
        </div>
      </div>
    </div>
  );
}

export default WindowAdBorder;
