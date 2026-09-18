// Fill client for the always-on ad border (SPR-07 M5).
//
// The border asks the backend what to paint in each reserved edge: a matched
// advertiser creative when one exists, else a HOUSE promo — a promotion of a
// genuinely servable, platform-authored book. House fill is the DEFAULT path,
// not a stub behind a "no fill" branch: zero buyers is the truth of v1, not an
// edge case (rigor #1, mirroring substrate/ad_inventory/reader_slots.py's
// fill_slot, which returns a HousePromo whenever no ad matches).
//
// The backend owns fill authority. The client sends only a window identity,
// lens and requested edges; it never supplies a price, advertiser, candidate,
// or winner. Network failure degrades to a visible house fill.

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
  fill_decision_id: string;
  slot_id: string;
  position: BorderPosition;
  kind: "ad" | "house";
  ad: AdCreative | null;
  house: HousePromo | null;
  revenue_usd_cents: number;
  price_status: "unpriced";
}

/** The four border edges, mirroring READER_AD_SLOT_POSITIONS. */
export type BorderPosition = "top" | "bottom" | "left" | "right";

/** Outcome of a fill request — never throws; the border always paints. */
/** Rank 0 website ads honesty (mirrors substrate rank0_honesty). */
export interface WebsiteAdsHonesty {
  surface: string;
  serving_model: string;
  max_sdk_on_web: boolean;
  fill_ladder: string[];
  price_status_default: string;
  revenue_usd_cents_until_pricing: number;
  pricing_gate: string;
  legal_gate: string;
  settlement_open?: boolean;
  settlement_path?: string;
  settlement_requires?: string[];
  speak_contributor_share: number;
  speak_platform_share: number;
  money_model: string;
  disbursement: string;
  decision_ref: string;
  spec_ref: string;
  rank01_decision_ref?: string;
}

export interface FillResult {
  fills: SlotFill[];
  /**
   * True when the fill came from the live route; false when the route was
   * absent/errored and we degraded to a synthesized house fill. Surfaced (not
   * hidden) so a story / a future operator surface can SEE the route is not
   * yet wired — honesty over a silent fallback.
   */
  served: boolean;
  /** Present when the fills route returned Rank 0 honesty. */
  honesty?: WebsiteAdsHonesty;
}

/** A neutral house fill for one edge, used when the route is absent. */
function houseFill(position: BorderPosition): SlotFill {
  return {
    fill_decision_id: "local-house",
    slot_id: `local:${position}`,
    position,
    kind: "house",
    ad: null,
    house: null,
    revenue_usd_cents: 0,
    price_status: "unpriced",
  };
}

const EXACT_RESPONSE_KEYS = new Set(["window_id", "fills", "honesty"]);
const LEGACY_RESPONSE_KEYS = new Set(["window_id", "fills"]);
const EXACT_FILL_KEYS = new Set([
  "fill_decision_id",
  "slot_id",
  "position",
  "kind",
  "ad",
  "house",
  "revenue_usd_cents",
  "price_status",
]);
const EXACT_AD_KEYS = new Set([
  "inventory_id", "advertiser_display_name", "creative_url", "landing_url",
]);
const EXACT_HOUSE_KEYS = new Set(["promoted_document_id", "title", "author"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, allowed: Set<string>): boolean {
  const keys = Object.keys(value);
  return keys.length === allowed.size && keys.every((key) => allowed.has(key));
}

function isHttpsUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 2048) return false;
  try { return new URL(value).protocol === "https:"; } catch { return false; }
}

/** Antiek-served creatives may be same-origin paths (manual sponsor mark). */
function isCreativeUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 2048 || !value) return false;
  if (value.startsWith("/") && !value.startsWith("//")) return true;
  return isHttpsUrl(value);
}

function parseAd(value: unknown): AdCreative | null {
  if (!isRecord(value) || !hasExactKeys(value, EXACT_AD_KEYS)) return null;
  if (
    typeof value.inventory_id !== "string" || !value.inventory_id ||
    typeof value.advertiser_display_name !== "string" || !value.advertiser_display_name ||
    !isCreativeUrl(value.creative_url) || !isHttpsUrl(value.landing_url)
  ) return null;
  return value as unknown as AdCreative;
}

function parseHouse(value: unknown): HousePromo | null | undefined {
  if (value === null) return null;
  if (!isRecord(value) || !hasExactKeys(value, EXACT_HOUSE_KEYS)) return undefined;
  for (const key of EXACT_HOUSE_KEYS) {
    const field = value[key];
    if (field !== null && typeof field !== "string") return undefined;
  }
  return value as HousePromo;
}

function parseHonesty(value: unknown): WebsiteAdsHonesty | undefined {
  if (!isRecord(value)) return undefined;
  if (value.surface !== "website") return undefined;
  if (value.serving_model !== "antiek_owned_creatives") return undefined;
  if (value.max_sdk_on_web !== false) return undefined;
  if (!Array.isArray(value.fill_ladder)) return undefined;
  if (value.price_status_default !== "unpriced") return undefined;
  if (value.revenue_usd_cents_until_pricing !== 0) return undefined;
  if (typeof value.pricing_gate !== "string") return undefined;
  if (typeof value.legal_gate !== "string") return undefined;
  if ("settlement_open" in value && value.settlement_open !== false) return undefined;
  if (typeof value.speak_contributor_share !== "number") return undefined;
  if (typeof value.speak_platform_share !== "number") return undefined;
  if (typeof value.money_model !== "string") return undefined;
  if (typeof value.disbursement !== "string") return undefined;
  if (typeof value.decision_ref !== "string") return undefined;
  if (typeof value.spec_ref !== "string") return undefined;
  return value as unknown as WebsiteAdsHonesty;
}

function parseFillResponse(
  value: unknown,
  windowId: string,
  requested: BorderPosition[],
): { fills: SlotFill[]; honesty?: WebsiteAdsHonesty } | null {
  if (!isRecord(value)) return null;
  const keysOk =
    hasExactKeys(value, EXACT_RESPONSE_KEYS) ||
    hasExactKeys(value, LEGACY_RESPONSE_KEYS);
  if (!keysOk) return null;
  if (value.window_id !== windowId || !Array.isArray(value.fills)) return null;
  const honesty = "honesty" in value ? parseHonesty(value.honesty) : undefined;
  if ("honesty" in value && honesty === undefined) return null;
  const requestedSet = new Set(requested);
  const seen = new Set<string>();
  const parsed: SlotFill[] = [];
  for (const raw of value.fills) {
    if (!isRecord(raw) || !hasExactKeys(raw, EXACT_FILL_KEYS)) return null;
    const position = raw.position;
    if (
      typeof position !== "string" ||
      !requestedSet.has(position as BorderPosition) ||
      seen.has(position)
    ) return null;
    if (raw.kind !== "ad" && raw.kind !== "house") return null;
    if (raw.revenue_usd_cents !== 0 || raw.price_status !== "unpriced") return null;
    if (typeof raw.fill_decision_id !== "string" || !raw.fill_decision_id) return null;
    if (typeof raw.slot_id !== "string" || !raw.slot_id) return null;
    const ad = parseAd(raw.ad);
    const house = parseHouse(raw.house);
    if (raw.kind === "ad" ? ad === null || raw.house !== null : raw.ad !== null || house === undefined) return null;
    seen.add(position);
    parsed.push({ ...(raw as unknown as SlotFill), ad, house: house ?? null });
  }
  if (seen.size !== requestedSet.size) return null;
  return { fills: parsed, honesty };
}

/**
 * Fetch the fills for the border's active edges. A 404 or any error degrades
 * to a neutral house fill per requested edge, so
 * the border always has something real to paint and never throws.
 */
export async function fetchFill(opts: {
  windowId: string;
  lens: Lens;
  positions: BorderPosition[];
  signal?: AbortSignal;
}): Promise<FillResult> {
  try {
    const resp = await apiFetch(`${API_BASE}/api/ad/fills`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        window_id: opts.windowId,
        lens: opts.lens,
        positions: opts.positions,
        document_id: null,
        page_index: null,
      }),
      signal: opts.signal,
    });
    if (!resp.ok) {
      // The border must remain usable when fill authority is unavailable.
      return { fills: opts.positions.map(houseFill), served: false };
    }
    const parsed = parseFillResponse(await resp.json(), opts.windowId, opts.positions);
    if (parsed === null) {
      return { fills: opts.positions.map(houseFill), served: false };
    }
    // Any edge the server didn't fill is house-filled here so every requested
    // edge always has a creative (house is the default, never blank).
    const byPos = new Map(parsed.fills.map((f) => [f.position, f]));
    return {
      fills: opts.positions.map((p) => byPos.get(p) ?? houseFill(p)),
      served: true,
      honesty: parsed.honesty,
    };
  } catch {
    return { fills: opts.positions.map(houseFill), served: false };
  }
}
