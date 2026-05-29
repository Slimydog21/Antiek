// Fill client for the always-on ad border (SPR-07 M5).
//
// The border asks the backend what to paint in each reserved edge: a matched
// advertiser creative when one exists, else a HOUSE promo — a promotion of a
// genuinely servable, platform-authored book. House fill is the DEFAULT path,
// not a stub behind a "no fill" branch: zero buyers is the truth of v1, not an
// edge case (rigor #1, mirroring substrate/ad_inventory/reader_slots.py's
// fill_slot, which returns a HousePromo whenever no ad matches).
//
// NAMED SEAM (handoff): the route `GET /api/ad/fill` DOES NOT EXIST YET. The
// backend has only advertiser-onboarding routes (interfaces/research/api/
// advertisers.py); the fill route is deferred to SPR-09. This client therefore
// DEGRADES GRACEFULLY: a 404 (route absent) or any network error resolves to a
// house fill, so the border is never blank and the app never crashes waiting
// on a route that isn't built. When SPR-09 lands the route, this client starts
// receiving real fills with no caller change.

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
 * Fetch the fills for the border's active edges. The route is a deferred seam:
 * a 404 or any error degrades to a neutral house fill per requested edge, so
 * the border always has something real to paint and never throws.
 */
export async function fetchFill(opts: {
  lens: Lens;
  positions: BorderPosition[];
  signal?: AbortSignal;
}): Promise<FillResult> {
  const params = new URLSearchParams({
    lens: opts.lens,
    positions: opts.positions.join(","),
  });
  try {
    const resp = await apiFetch(`${API_BASE}/api/ad/fill?${params.toString()}`, {
      method: "GET",
      signal: opts.signal,
    });
    if (!resp.ok) {
      // Route absent (404, the SPR-09 seam) or a server error: degrade to
      // house. NOT a thrown error — the border must always paint.
      return { fills: opts.positions.map(houseFill), served: false };
    }
    const body = (await resp.json()) as { fills?: SlotFill[] };
    const fills = Array.isArray(body.fills) ? body.fills : [];
    // Any edge the server didn't fill is house-filled here so every requested
    // edge always has a creative (house is the default, never blank).
    const byPos = new Map(fills.map((f) => [f.position, f]));
    return {
      fills: opts.positions.map((p) => byPos.get(p) ?? houseFill(p)),
      served: true,
    };
  } catch {
    return { fills: opts.positions.map(houseFill), served: false };
  }
}
