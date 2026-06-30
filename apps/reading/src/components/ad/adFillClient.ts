// Fill client for the always-on ad border (SPR-07 M5).
//
// The border asks the backend what to paint in each reserved edge: a matched
// advertiser creative when one exists, else a HOUSE promo — a promotion of a
// genuinely servable, platform-authored book. House fill is the DEFAULT path,
// not a stub behind a "no fill" branch: zero buyers is the truth of v1, not an
// edge case (rigor #1, mirroring substrate/ad_inventory/reader_slots.py's
// fill_slot, which returns a HousePromo whenever no ad matches).
//
// LIVE ROUTE: `GET /api/ad/fill` exists in interfaces/research/api/ad_routes.py.
// It fills ONE reader slot at a time (`document_id`, `page_index`, `position`).
// This client fans out across the active edges and still DEGRADES GRACEFULLY:
// when there is no current reader document/page, the route is absent, or a
// network error occurs, each requested edge gets a neutral house fill. The
// border is therefore never blank, but the live route is used whenever the
// shell can name the active reader slot.

import { API_BASE, apiFetch } from "../../lib/api";
import type { Lens } from "./frameContract";

/**
 * The advertiser creative a paid fill carries. A read-only subset of the
 * backend ``ad_bidding.AdInventoryItem`` — only the fields a border creative
 * renders. ``landing_url`` is where a click goes; ``creative_url`` is the
 * banner image (rendered statically — no autoplay, reduced-motion-safe).
 */
export interface AdCreative {
  inventory_id: string;
  advertiser_display_name: string;
  creative_url: string;
  landing_url: string;
}

/**
 * The zero-buyer house fill. Mirrors ``reader_slots.HousePromo``: a promotion
 * of a servable book, carrying enough to render a real, useful card (never
 * blank/filler). All fields may be absent — the backend's _pick_house_promo
 * returns None when there is nothing to promote, in which case the border
 * renders a neutral house card (still a real house second, still telemetered).
 *
 * §9.0: this carries promo DISPLAY (title/author of a servable book), never
 * gated body text. The backend only ever promotes servable books.
 */
export interface HousePromo {
  promoted_document_id?: string | null;
  title?: string | null;
  author?: string | null;
}

/**
 * What fills one border edge. Mirrors ``reader_slots.SlotFill``: ``kind`` is
 * 'ad' (a paid creative) or 'house' (the zero-buyer default). Exactly one of
 * ``ad`` / ``house`` is meaningful. ``revenue_usd_cents`` is what the
 * advertiser pays — 0 for house (the honest default, no invented money).
 */
export interface SlotFill {
  slot_id?: string;
  document_id?: string;
  page_index?: number;
  position: BorderPosition;
  kind: "ad" | "house";
  ad?: AdCreative | null;
  house?: HousePromo | null;
  revenue_usd_cents: number;
}

/** The four border edges, mirroring READER_AD_SLOT_POSITIONS. */
export type BorderPosition = "top" | "bottom" | "left" | "right";

/** Outcome of a fill request — never throws; the border always paints. */
export interface FillResult {
  fills: SlotFill[];
  /**
   * True when the fill came from the live route; false when the route was
   * absent/errored and we degraded to a synthesized house fill. Surfaced (not
   * hidden) so a story / a future operator surface can SEE the route is not
   * yet wired — honesty over a silent fallback.
   */
  served: boolean;
}

/** A neutral house fill for one edge, used when the route is absent. */
function houseFill(position: BorderPosition): SlotFill {
  return { position, kind: "house", house: null, revenue_usd_cents: 0 };
}

/**
 * Fetch the fills for the border's active reader edges. The live backend route
 * fills one edge per request; a missing reader document, 404, or any error
 * degrades to neutral house per requested edge, so the border always paints.
 */
export async function fetchFill(opts: {
  lens: Lens;
  documentId?: string | null;
  pageIndex?: number | null;
  positions: BorderPosition[];
  signal?: AbortSignal;
}): Promise<FillResult> {
  if (!opts.documentId || opts.pageIndex === undefined || opts.pageIndex === null) {
    return { fills: opts.positions.map(houseFill), served: false };
  }
  try {
    const results = await Promise.all(
      opts.positions.map(async (position) => {
        const params = new URLSearchParams({
          document_id: opts.documentId as string,
          page_index: String(opts.pageIndex),
          position,
        });
        const resp = await apiFetch(`${API_BASE}/api/ad/fill?${params.toString()}`, {
          method: "GET",
          signal: opts.signal,
        });
        if (!resp.ok) return { fill: houseFill(position), served: false };
        const body = (await resp.json()) as SlotFill;
        return {
          fill: body?.position === position ? body : houseFill(position),
          served: body?.position === position,
        };
      }),
    );
    return {
      fills: results.map((r) => r.fill),
      served: results.some((r) => r.served),
    };
  } catch {
    return { fills: opts.positions.map(houseFill), served: false };
  }
}
