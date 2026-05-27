/**
 * RESERVED — M4 (theme grouping) is DEFERRED. This component + the
 * `region_id`/`region_label` schema fields are the forward-compatible seam; it
 * is NOT mounted today because SPR-03 shipped no region-assign gesture. A
 * future sprint adds a multi-select→group→label gesture that emits
 * `block.positioned` with a shared `region_id`, then mounts this. See
 * docs/decisions/spr-03-block-canvas-lineage.md.
 *
 * ThemeRegion — whiteboard-style theme grouping for the DRW block-canvas
 * (Living Roadmap SPR-03 M4, the lowest-priority + cuttable milestone).
 *
 * A region is a labelled rectangle drawn behind a set of blocks that share a
 * `regionId`. It does NOT own a store: grouping rides the SAME typed event as
 * position — `BlockPositionPayload.region_id` / `.region_label` — so there is
 * exactly one event type and zero side stores (the single-writer reason is
 * documented on the payload in substrate/schemas/events.py and at the
 * Canvas.tsx persist call site). The region's geometry is DERIVED from its
 * member blocks' positions (`regionBounds`), so dragging a member re-flows
 * the region automatically with no extra persistence.
 *
 * This component is purely presentational — Canvas computes the member sets
 * and bounds and feeds them in. If M4 were cut, deleting this file and its
 * Canvas usage leaves M1–M3 intact (the region_id field on the event simply
 * goes unused).
 */

import { regionBounds, type BlockPosition } from "./canvasLayout";

export interface ThemeRegionData {
  regionId: string;
  label: string | null;
  /** Resolved positions of the blocks that belong to this region. */
  members: BlockPosition[];
}

export interface ThemeRegionProps {
  region: ThemeRegionData;
}

export default function ThemeRegion({ region }: ThemeRegionProps) {
  const bounds = regionBounds(region.members);
  // A region with no members has no honest geometry — render nothing rather
  // than a zero-size box.
  if (!bounds) return null;

  return (
    <div
      data-theme-region={region.regionId}
      className="pointer-events-none absolute rounded-hog border-edge border-dashed border-aurora/50 bg-aurora/5"
      style={{
        left: bounds.x,
        top: bounds.y,
        width: bounds.width,
        height: bounds.height,
        zIndex: 0,
      }}
    >
      <span className="absolute -top-2 left-2 bg-ice-0 px-1 font-mono text-[10px] uppercase tracking-wider text-aurora dark:bg-charcoal-2">
        {region.label || region.regionId}
      </span>
    </div>
  );
}
