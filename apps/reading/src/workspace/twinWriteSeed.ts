/**
 * twinWriteSeed — session-scoped handoff from TwinNotes multi-select draft
 * into Write mode (residual pp).
 *
 * Stores HTML + plain text twin draft payload in sessionStorage so the Write
 * door can seed brainstorm without inventing server document ids. Pure
 * client; offline-honest; HTML-first.
 */

export const TWIN_WRITE_SEED_KEY_PREFIX = "antiek.twin_write_seed.";

export type TwinWriteSeedPayload = {
  plain_text: string;
  html: string;
  title: string;
  asset_id: string;
  note_ids: string[];
  view_format: "html";
  source: "twin_draft_selected";
};

/** Build a unique sessionStorage key (never invent twin content). */
export function makeTwinWriteSeedKey(): string {
  return `${TWIN_WRITE_SEED_KEY_PREFIX}${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Persist twin draft seed. Returns key for `?twin_seed=` handoff, or null if
 * storage unavailable / empty plain_text.
 */
export function storeTwinWriteSeed(input: {
  plain_text: string;
  html: string;
  title: string;
  asset_id: string;
  note_ids: readonly string[];
}): string | null {
  const plain = String(input.plain_text || "").trim();
  if (!plain) return null;
  if (typeof window === "undefined" || !window.sessionStorage) return null;
  const key = makeTwinWriteSeedKey();
  const payload: TwinWriteSeedPayload = {
    plain_text: plain.slice(0, 16000),
    html: String(input.html || "").slice(0, 100000),
    title: String(input.title || "").trim() || "Twin draft",
    asset_id: String(input.asset_id || "").trim(),
    note_ids: [...input.note_ids].map((x) => String(x || "").trim()).filter(Boolean),
    view_format: "html",
    source: "twin_draft_selected",
  };
  try {
    window.sessionStorage.setItem(key, JSON.stringify(payload));
    return key;
  } catch {
    return null;
  }
}

/** Load twin seed by key; returns null on miss/corrupt/empty. */
export function loadTwinWriteSeed(key: string): TwinWriteSeedPayload | null {
  const k = String(key || "").trim();
  if (!k || !k.startsWith(TWIN_WRITE_SEED_KEY_PREFIX)) return null;
  if (typeof window === "undefined" || !window.sessionStorage) return null;
  try {
    const raw = window.sessionStorage.getItem(k);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<TwinWriteSeedPayload>;
    const plain = String(parsed.plain_text || "").trim();
    if (!plain) return null;
    return {
      plain_text: plain,
      html: String(parsed.html || ""),
      title: String(parsed.title || "Twin draft").trim() || "Twin draft",
      asset_id: String(parsed.asset_id || "").trim(),
      note_ids: Array.isArray(parsed.note_ids)
        ? parsed.note_ids.map((x) => String(x || "").trim()).filter(Boolean)
        : [],
      view_format: "html",
      source: "twin_draft_selected",
    };
  } catch {
    return null;
  }
}

/** Write door URL for twin seed handoff. */
export function buildTwinWriteHref(seedKey: string): string {
  const k = String(seedKey || "").trim();
  if (!k) return "/write";
  return `/write?twin_seed=${encodeURIComponent(k)}`;
}
