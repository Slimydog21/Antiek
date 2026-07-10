/**
 * twinWriteSeed — session-scoped handoff from TwinNotes multi-select draft
 * into Write mode (residual pp).
 *
 * Stores HTML + plain text twin draft payload in sessionStorage so the Write
 * door can seed brainstorm without inventing server document ids. Pure
 * client; offline-honest; HTML-first.
 */

export const TWIN_WRITE_SEED_KEY_PREFIX = "antiek.twin_write_seed.";

export type TwinWriteSeedSource =
  | "twin_draft_selected"
  | "midnight_oil_deposit"
  | "collective_doc_merge"
  | "marketplace_host"
  | "spawn_merge"
  | "hosted_html_document"
  | "deep_research_session"
  | "research_progress_complete";

export type TwinWriteSeedPayload = {
  plain_text: string;
  html: string;
  title: string;
  asset_id: string;
  note_ids: string[];
  view_format: "html";
  source: TwinWriteSeedSource;
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
  /** Residual (pz): provenance for MO deposit / merge dual handoff. */
  source?: TwinWriteSeedSource;
}): string | null {
  const plain = String(input.plain_text || "").trim();
  if (!plain) return null;
  if (typeof window === "undefined" || !window.sessionStorage) return null;
  const key = makeTwinWriteSeedKey();
  const allowed: TwinWriteSeedSource[] = [
    "midnight_oil_deposit",
    "collective_doc_merge",
    "marketplace_host",
    "spawn_merge",
    "hosted_html_document",
    "deep_research_session",
    "research_progress_complete",
  ];
  const source: TwinWriteSeedSource = allowed.includes(
    input.source as TwinWriteSeedSource,
  )
    ? (input.source as TwinWriteSeedSource)
    : "twin_draft_selected";
  const payload: TwinWriteSeedPayload = {
    plain_text: plain.slice(0, 16000),
    html: String(input.html || "").slice(0, 100000),
    title: String(input.title || "").trim() || "Twin draft",
    asset_id: String(input.asset_id || "").trim(),
    note_ids: [...input.note_ids].map((x) => String(x || "").trim()).filter(Boolean),
    view_format: "html",
    source,
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
    const srcRaw = String(parsed.source || "twin_draft_selected").trim();
    const allowedLoad: TwinWriteSeedSource[] = [
      "midnight_oil_deposit",
      "collective_doc_merge",
      "marketplace_host",
      "spawn_merge",
      "hosted_html_document",
      "deep_research_session",
      "research_progress_complete",
    ];
    const source: TwinWriteSeedSource = allowedLoad.includes(
      srcRaw as TwinWriteSeedSource,
    )
      ? (srcRaw as TwinWriteSeedSource)
      : "twin_draft_selected";
    return {
      plain_text: plain,
      html: String(parsed.html || ""),
      title: String(parsed.title || "Twin draft").trim() || "Twin draft",
      asset_id: String(parsed.asset_id || "").trim(),
      note_ids: Array.isArray(parsed.note_ids)
        ? parsed.note_ids.map((x) => String(x || "").trim()).filter(Boolean)
        : [],
      view_format: "html",
      source,
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

/**
 * Residual (pz / FUTURE-AGENT V6): Write URL combining hosted html_draft
 * document_id with optional twin_seed session key so create seeds twins when
 * empty (html import + brainstorm seed dual handoff).
 */
export function buildWriteHtmlDraftHref(opts: {
  documentId: string;
  twinSeedKey?: string | null;
}): string {
  const doc = String(opts.documentId || "").trim();
  if (!doc) return "/write";
  const params = new URLSearchParams();
  params.set("html_draft", doc);
  const seed = String(opts.twinSeedKey || "").trim();
  if (seed) params.set("twin_seed", seed);
  return `/write?${params.toString()}`;
}

/**
 * Residual (pz): strip tags for twin_seed plain_text from HTML deposit body.
 * Never invents content; empty HTML → empty string.
 */
export function plainTextFromHtml(html: string, maxLen = 16000): string {
  return String(html || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLen);
}

/**
 * Residual (qc / FUTURE-AGENT V5): dual Write handoff for marketplace host /
 * library HTML docs — html_draft + optional twin_seed (parity MO pz).
 */
export function buildMarketplaceWriteHref(opts: {
  documentId: string;
  title?: string | null;
  html?: string | null;
}): string {
  const doc = String(opts.documentId || "").trim();
  if (!doc) return "/write";
  const plain =
    plainTextFromHtml(opts.html || "") ||
    String(opts.title || "").trim() ||
    doc;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html: String(opts.html || ""),
    title: String(opts.title || "").trim() || `Marketplace · ${doc}`,
    asset_id: doc,
    note_ids: [],
    source: "marketplace_host",
  });
  return buildWriteHtmlDraftHref({
    documentId: doc,
    twinSeedKey: seedKey,
  });
}

/**
 * Residual (qd): dual Write handoff for spawn-merge / collective draft docs.
 */
export function buildMergedDocWriteHref(opts: {
  documentId: string;
  title?: string | null;
  html?: string | null;
  source?: "spawn_merge" | "collective_doc_merge";
}): string {
  const doc = String(opts.documentId || "").trim();
  if (!doc) return "/write";
  const plain =
    plainTextFromHtml(opts.html || "") ||
    String(opts.title || "").trim() ||
    doc;
  const src = opts.source === "collective_doc_merge" ? opts.source : "spawn_merge";
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html: String(opts.html || ""),
    title: String(opts.title || "").trim() || `Merged research · ${doc}`,
    asset_id: doc,
    note_ids: [],
    source: src,
  });
  return buildWriteHtmlDraftHref({
    documentId: doc,
    twinSeedKey: seedKey,
  });
}

/**
 * Residual (qu): dual Write handoff for hosted HTML reading assets
 * (html_draft + twin_seed; parity marketplace qc / MO pz).
 */
export function buildHostedHtmlWriteHref(opts: {
  documentId: string;
  title?: string | null;
  html?: string | null;
}): string {
  const doc = String(opts.documentId || "").trim();
  if (!doc) return "/write";
  const plain =
    plainTextFromHtml(opts.html || "") ||
    String(opts.title || "").trim() ||
    doc;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html: String(opts.html || ""),
    title: String(opts.title || "").trim() || `Hosted HTML · ${doc}`,
    asset_id: doc,
    note_ids: [],
    source: "hosted_html_document",
  });
  return buildWriteHtmlDraftHref({
    documentId: doc,
    twinSeedKey: seedKey,
  });
}

/**
 * Residual (qv): Write handoff from deep_research_session (selection + goal).
 * twin_seed only — does not invent a server document_id for unfinished sessions.
 */
export function buildDeepResearchWriteHref(opts: {
  selectionText?: string | null;
  goal?: string | null;
  spawnId?: string | null;
  parentAssetId?: string | null;
}): string | null {
  const selection = String(opts.selectionText || "").trim();
  const goal = String(opts.goal || "").trim();
  const plain = [selection, goal].filter(Boolean).join("\n\n");
  if (!plain) return null;
  const spawn = String(opts.spawnId || "").trim() || "spawn";
  const asset =
    String(opts.parentAssetId || "").trim() || `deep_research:${spawn}`;
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const html =
    `<article data-view-format="html" data-source="deep_research_session" data-spawn-id="${escape(spawn)}">` +
    `<h1>Deep research seed · ${escape(spawn)}</h1>` +
    (goal ? `<p class="goal"><strong>Goal:</strong> ${escape(goal)}</p>` : "") +
    (selection
      ? `<section class="selection"><h2>Selection</h2><pre>${escape(selection)}</pre></section>`
      : "") +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Deep research · ${spawn}`,
    asset_id: asset,
    note_ids: [],
    source: "deep_research_session",
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (qw): Write handoff when research progress reaches terminal.
 * twin_seed only — progress HTML/events seed the recursive note-taker;
 * does not invent a server document_id until Write create.
 */
export function buildResearchProgressWriteHref(opts: {
  spawnId: string;
  parentAssetId?: string | null;
  researchTier?: string | null;
  latestStage?: string | null;
  isTerminal: boolean;
  events?: ReadonlyArray<{
    stage?: string | null;
    message?: string | null;
    sequence?: number | null;
  }>;
  html?: string | null;
  goal?: string | null;
}): string | null {
  if (!opts.isTerminal) return null;
  const spawn = String(opts.spawnId || "").trim();
  if (!spawn) return null;
  const goal = String(opts.goal || "").trim();
  const stage = String(opts.latestStage || "").trim();
  const tier = String(opts.researchTier || "").trim();
  const events = opts.events || [];
  const eventLines = events
    .map((e) => {
      const st = String(e.stage || "").trim();
      const msg = String(e.message || "").trim();
      if (!st && !msg) return "";
      return st ? `[${st}] ${msg}` : msg;
    })
    .filter(Boolean);
  const plainParts = [
    goal ? `Goal: ${goal}` : "",
    `Spawn: ${spawn}`,
    stage ? `Terminal stage: ${stage}` : "Terminal: complete",
    tier ? `Tier: ${tier}` : "",
    ...eventLines,
  ].filter(Boolean);
  const plainFromHtml = plainTextFromHtml(opts.html || "");
  const plain =
    plainParts.join("\n") +
    (plainFromHtml ? `\n\n${plainFromHtml}` : "");
  if (!plain.trim()) return null;
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const eventHtml = eventLines
    .map((line) => `<li>${escape(line)}</li>`)
    .join("");
  const bodyHtml =
    String(opts.html || "").trim() ||
    (eventHtml
      ? `<ol class="progress-events">${eventHtml}</ol>`
      : `<p>Deep research terminal · ${escape(spawn)}</p>`);
  const html =
    `<article data-view-format="html" data-source="research_progress_complete" data-spawn-id="${escape(spawn)}" data-is-terminal="true">` +
    `<h1>Research complete · ${escape(spawn)}</h1>` +
    (goal ? `<p class="goal"><strong>Goal:</strong> ${escape(goal)}</p>` : "") +
    (stage
      ? `<p class="stage"><strong>Stage:</strong> ${escape(stage)}</p>`
      : "") +
    (tier ? `<p class="tier"><strong>Tier:</strong> ${escape(tier)}</p>` : "") +
    bodyHtml +
    `</article>`;
  const asset =
    String(opts.parentAssetId || "").trim() || `deep_research:${spawn}`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Research complete · ${spawn}`,
    asset_id: asset,
    note_ids: [],
    source: "research_progress_complete",
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}
