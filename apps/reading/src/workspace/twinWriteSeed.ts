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
  // Residual (aaj): catalog HTML projection float → Write seed (filter-aware listing).
  | "marketplace_catalog"
  | "spawn_merge"
  | "hosted_html_document"
  | "deep_research_session"
  | "research_progress_complete"
  | "research_progress_draft"
  | "evidence_pack"
  | "publication_hydrate"
  | "session_flywheel_complete"
  | "context_search"
  | "research_context_pack"
  | "twin_promote_context"
  // Residual (tu): multi-spawn cohesive unit prompt float → Write seed (tt catalog).
  | "collective_unit_prompt"
  // Residual (vd): recursive note-taker cross-asset merge → Write seed.
  | "twin_cross_asset_merge"
  // Residual (vk): collective written analysis float → Write seed.
  | "collective_written_analysis";

export type TwinWriteSeedPayload = {
  plain_text: string;
  html: string;
  title: string;
  asset_id: string;
  note_ids: string[];
  view_format: "html";
  source: TwinWriteSeedSource;
  /**
   * Residual (adq): body honesty for Antiek-bench rewrite feed when Write
   * lands and seedTwinNotes records usage_source. Title-only Open Write paths
   * must stamp false so plain_text fallback titles are not mis-inferred true.
   */
  has_body: boolean;
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
  /**
   * Residual (adq): optional body honesty. When omitted, true only when HTML
   * body text is non-empty OR plain_text is not a pure title/asset fallback.
   */
  has_body?: boolean;
}): string | null {
  const plain = String(input.plain_text || "").trim();
  if (!plain) return null;
  if (typeof window === "undefined" || !window.sessionStorage) return null;
  const key = makeTwinWriteSeedKey();
  const allowed: TwinWriteSeedSource[] = [
    "twin_draft_selected",
    "midnight_oil_deposit",
    "collective_doc_merge",
    "marketplace_host",
    "marketplace_catalog",
    "spawn_merge",
    "hosted_html_document",
    "deep_research_session",
    "research_progress_complete",
    "research_progress_draft",
    "evidence_pack",
    "publication_hydrate",
    "session_flywheel_complete",
    "context_search",
    "research_context_pack",
    "twin_promote_context",
    // Residual (tu): cohesive unit prompt must not collapse to twin_draft_selected.
    "collective_unit_prompt",
    // Residual (vd): cross-asset twin merge provenance.
    "twin_cross_asset_merge",
    // Residual (vk): collective written analysis float.
    "collective_written_analysis",
  ];
  const source: TwinWriteSeedSource = allowed.includes(
    input.source as TwinWriteSeedSource,
  )
    ? (input.source as TwinWriteSeedSource)
    : "twin_draft_selected";
  const title = String(input.title || "").trim() || "Twin draft";
  const assetId = String(input.asset_id || "").trim();
  const htmlPlain = plainTextFromHtml(String(input.html || ""));
  // Residual (adq): default body honesty — HTML body wins; else plain that is
  // not merely the title/asset_id fallback (title-only Open Write → false).
  const hasBody =
    input.has_body !== undefined
      ? Boolean(input.has_body)
      : Boolean(
          htmlPlain.trim() ||
            (plain !== title &&
              plain !== assetId &&
              plain.length > Math.max(title.length, assetId.length)),
        );
  const payload: TwinWriteSeedPayload = {
    plain_text: plain.slice(0, 16000),
    html: String(input.html || "").slice(0, 100000),
    title,
    asset_id: assetId,
    note_ids: [...input.note_ids].map((x) => String(x || "").trim()).filter(Boolean),
    view_format: "html",
    source,
    has_body: hasBody,
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
      "twin_draft_selected",
      "midnight_oil_deposit",
      "collective_doc_merge",
      "marketplace_host",
      "marketplace_catalog",
      "spawn_merge",
      "hosted_html_document",
      "deep_research_session",
      "research_progress_complete",
      "research_progress_draft",
      "evidence_pack",
      "publication_hydrate",
      "session_flywheel_complete",
      "context_search",
      "research_context_pack",
      "twin_promote_context",
      // Residual (tu): load parity with store allowlist.
      "collective_unit_prompt",
      // Residual (vd): cross-asset twin merge provenance.
      "twin_cross_asset_merge",
      // Residual (vk): collective written analysis float.
      "collective_written_analysis",
    ];
    const source: TwinWriteSeedSource = allowedLoad.includes(
      srcRaw as TwinWriteSeedSource,
    )
      ? (srcRaw as TwinWriteSeedSource)
      : "twin_draft_selected";
    const title = String(parsed.title || "Twin draft").trim() || "Twin draft";
    const assetId = String(parsed.asset_id || "").trim();
    const html = String(parsed.html || "");
    const htmlPlain = plainTextFromHtml(html);
    // Residual (adq): legacy seeds without has_body use same default rule as store.
    let hasBody: boolean;
    if (typeof parsed.has_body === "boolean") {
      hasBody = parsed.has_body;
    } else {
      hasBody = Boolean(
        htmlPlain.trim() ||
          (plain !== title &&
            plain !== assetId &&
            plain.length > Math.max(title.length, assetId.length)),
      );
    }
    return {
      plain_text: plain,
      html,
      title,
      asset_id: assetId,
      note_ids: Array.isArray(parsed.note_ids)
        ? parsed.note_ids.map((x) => String(x || "").trim()).filter(Boolean)
        : [],
      view_format: "html",
      source,
      has_body: hasBody,
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
 * Residual (qx): freeform provenance stamp for Write project type.
 * Includes source so deep_research_session / research_progress_complete /
 * marketplace dual handoffs are auditable on the writing asset.
 */
export function formatTwinWriteSeedFreeform(
  seed: Pick<TwinWriteSeedPayload, "source" | "asset_id" | "note_ids">,
): string {
  const src = String(seed.source || "twin_draft_selected").trim() || "twin_draft_selected";
  const asset = String(seed.asset_id || "asset").trim() || "asset";
  const n = Array.isArray(seed.note_ids) ? seed.note_ids.length : 0;
  // source + note count before asset so asset may contain colons (deep_research:spawn).
  return `twin_seed:${src}:${n}:${asset}`;
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
  const fromHtml = plainTextFromHtml(opts.html || "");
  const plain =
    fromHtml ||
    String(opts.title || "").trim() ||
    doc;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html: String(opts.html || ""),
    title: String(opts.title || "").trim() || `Marketplace · ${doc}`,
    asset_id: doc,
    note_ids: [],
    source: "marketplace_host",
    // Residual (adq): title-only host (no HTML body) → has_body false.
    has_body: Boolean(fromHtml),
  });
  return buildWriteHtmlDraftHref({
    documentId: doc,
    twinSeedKey: seedKey,
  });
}

/**
 * Residual (qd): dual Write handoff for spawn-merge / collective draft docs.
 * Residual (afg): collective written analysis may pass source=
 * collective_written_analysis (do not collapse to collective_doc_merge).
 */
export function buildMergedDocWriteHref(opts: {
  documentId: string;
  title?: string | null;
  html?: string | null;
  source?:
    | "spawn_merge"
    | "collective_doc_merge"
    | "collective_written_analysis";
}): string {
  const doc = String(opts.documentId || "").trim();
  if (!doc) return "/write";
  const fromHtml = plainTextFromHtml(opts.html || "");
  const plain =
    fromHtml ||
    String(opts.title || "").trim() ||
    doc;
  // Residual (afg): preserve written analysis Write-seed provenance.
  const src: TwinWriteSeedSource =
    opts.source === "collective_written_analysis"
      ? "collective_written_analysis"
      : opts.source === "collective_doc_merge"
        ? "collective_doc_merge"
        : "spawn_merge";
  const defaultTitle =
    src === "collective_written_analysis"
      ? `Written analysis · ${doc}`
      : `Merged research · ${doc}`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html: String(opts.html || ""),
    title: String(opts.title || "").trim() || defaultTitle,
    asset_id: doc,
    note_ids: [],
    source: src,
    // Residual (adq): title-only merge (no HTML body) → has_body false.
    has_body: Boolean(fromHtml),
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
  /**
   * Residual (si): when floating evidence packs Open Write, pass
   * source=evidence_pack so Antiek-bench records citation-trust Write seeds
   * (default remains hosted_html_document).
   */
  source?: string | null;
}): string {
  const doc = String(opts.documentId || "").trim();
  if (!doc) return "/write";
  const fromHtml = plainTextFromHtml(opts.html || "");
  const plain =
    fromHtml ||
    String(opts.title || "").trim() ||
    doc;
  const srcRaw = String(opts.source || "").trim();
  // Residual (si/sj/vg): preserve known Write-seed sources from float hosts.
  // Residual (aai): marketplace library / rehydrate windows alias to
  // marketplace_host for Antiek-bench write-seed feed (same account host path).
  const MARKETPLACE_HOST_WRITE_ALIASES = new Set([
    "marketplace_host",
    "marketplace_library",
    "marketplace_library_rehydrate",
  ]);
  const KNOWN_HOST_WRITE_SOURCES = new Set([
    "evidence_pack",
    "context_search",
    "publication_hydrate",
    "research_context_pack",
    "research_progress_complete",
    "research_progress_draft",
    "session_flywheel_complete",
    // Residual (tr): multi-spawn cohesive unit prompt float (not doc merge).
    "collective_unit_prompt",
    // Residual (vg): recursive note-taker twin draft floats → Write seed.
    "twin_draft_selected",
    "twin_cross_asset_merge",
    // Residual (vk): collective written analysis float → Write seed.
    "collective_written_analysis",
    // Residual (vp): spawn/collective document merge floats → Write seed.
    "spawn_merge",
    "collective_doc_merge",
    // Residual (vr): marketplace host + MO deposit floats → Write seed.
    "marketplace_host",
    "midnight_oil_deposit",
    // Residual (aai): library surface aliases (normalized below).
    "marketplace_library",
    "marketplace_library_rehydrate",
    // Residual (aaj): catalog HTML projection float → Write seed.
    "marketplace_catalog",
  ]);
  const source = MARKETPLACE_HOST_WRITE_ALIASES.has(srcRaw)
    ? "marketplace_host"
    : KNOWN_HOST_WRITE_SOURCES.has(srcRaw)
      ? srcRaw
      : "hosted_html_document";
  const titleDefault =
    source === "evidence_pack"
      ? `Evidence pack · ${doc}`
      : source === "context_search"
        ? `Context search · ${doc}`
        : source === "publication_hydrate"
          ? `Hydrated publication · ${doc}`
          : source === "research_context_pack"
            ? `Research context pack · ${doc}`
            : source === "research_progress_complete" ||
                source === "research_progress_draft"
              ? `Research progress · ${doc}`
              : source === "collective_unit_prompt"
                ? `Collective cohesive unit · ${doc}`
                : source === "session_flywheel_complete"
                  ? `Session flywheel · ${doc}`
                  : source === "twin_cross_asset_merge"
                    ? `Twin cross-asset merge · ${doc}`
                    : source === "twin_draft_selected"
                      ? `Twin draft · ${doc}`
                      : source === "collective_written_analysis"
                        ? `Collective written analysis · ${doc}`
                        : source === "spawn_merge"
                          ? `Spawn merge · ${doc}`
                          : source === "collective_doc_merge"
                            ? `Collective document merge · ${doc}`
                            : source === "marketplace_host"
                              ? `Marketplace host · ${doc}`
                              : source === "marketplace_catalog"
                                ? `Marketplace catalog · ${doc}`
                                : source === "midnight_oil_deposit"
                                  ? `Midnight Oil deposit · ${doc}`
                                  : `Hosted HTML · ${doc}`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html: String(opts.html || ""),
    title: String(opts.title || "").trim() || titleDefault,
    asset_id: doc,
    note_ids: [],
    source: source as TwinWriteSeedSource,
    // Residual (adq): title-only hosted Open Write → has_body false.
    has_body: Boolean(fromHtml),
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
    // Residual (aei): builder only returns when plain non-empty → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (qw): Write handoff when research progress reaches terminal.
 * Residual (rp): mid-flight draft seed when allowInProgress + events/html.
 * twin_seed only — does not invent a server document_id until Write create.
 */
export function buildResearchProgressWriteHref(opts: {
  spawnId: string;
  parentAssetId?: string | null;
  researchTier?: string | null;
  latestStage?: string | null;
  isTerminal: boolean;
  /** Residual (rp): allow non-terminal plan→cite draft Write seed. */
  allowInProgress?: boolean;
  events?: ReadonlyArray<{
    stage?: string | null;
    message?: string | null;
    sequence?: number | null;
  }>;
  html?: string | null;
  goal?: string | null;
}): string | null {
  if (!opts.isTerminal && !opts.allowInProgress) return null;
  const spawn = String(opts.spawnId || "").trim();
  if (!spawn) return null;
  const source: TwinWriteSeedSource = opts.isTerminal
    ? "research_progress_complete"
    : "research_progress_draft";
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
  const stageLabel = opts.isTerminal
    ? stage
      ? `Terminal stage: ${stage}`
      : "Terminal: complete"
    : stage
      ? `In-progress stage: ${stage}`
      : "In-progress: draft";
  const plainParts = [
    goal ? `Goal: ${goal}` : "",
    `Spawn: ${spawn}`,
    stageLabel,
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
      : `<p>Deep research ${opts.isTerminal ? "terminal" : "draft"} · ${escape(spawn)}</p>`);
  const title = opts.isTerminal
    ? `Research complete · ${spawn}`
    : `Research draft · ${spawn}`;
  const html =
    `<article data-view-format="html" data-source="${source}" data-spawn-id="${escape(spawn)}" data-is-terminal="${opts.isTerminal ? "true" : "false"}">` +
    `<h1>${escape(title)}</h1>` +
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
    title,
    asset_id: asset,
    note_ids: [],
    source,
    // Residual (aei): progress seed only when plain non-empty → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (rb): Write handoff from evidence pack (insights + questions + refs).
 * twin_seed only — HTML-first competitive citation substrate into Write.
 */
export function buildEvidencePackWriteHref(opts: {
  assetId: string;
  spawnId?: string | null;
  insights?: ReadonlyArray<string | null | undefined>;
  questions?: ReadonlyArray<string | null | undefined>;
  sourceReferences?: ReadonlyArray<{
    title?: string | null;
    title_hint?: string | null;
    url?: string | null;
    canonical_url?: string | null;
    raw?: string | null;
    kind?: string | null;
    source?: string | null;
  } | null | undefined>;
  html?: string | null;
  researchTier?: string | null;
}): string | null {
  const asset = String(opts.assetId || "").trim();
  if (!asset) return null;
  const insights = (opts.insights || [])
    .map((x) => String(x || "").trim())
    .filter(Boolean);
  const questions = (opts.questions || [])
    .map((x) => String(x || "").trim())
    .filter(Boolean);
  const refs = (opts.sourceReferences || [])
    .map((r) => {
      if (!r) return "";
      const title = String(r.title || r.title_hint || r.raw || "").trim();
      const url = String(r.url || r.canonical_url || "").trim();
      const src = String(r.source || r.kind || "").trim();
      if (!title && !url) return "";
      return [title, url, src ? `(${src})` : ""].filter(Boolean).join(" ");
    })
    .filter(Boolean);
  // Residual (aji/air): multi-hop chain honesty on Write seed (never invent edges).
  // Empty packs (no insights/questions/refs/html) stay null — never invent substrate.
  if (
    insights.length === 0 &&
    questions.length === 0 &&
    refs.length === 0 &&
    !String(opts.html || "").trim()
  ) {
    return null;
  }
  const chainComplete = insights.length > 0 && refs.length > 0;
  const hopStrip = [
    insights.length ? `Insights (claims)(${insights.length})` : "",
    questions.length ? `Open questions(${questions.length})` : "",
    refs.length ? `Source references(${refs.length})` : "",
  ]
    .filter(Boolean)
    .join(" → ");
  const plainParts = [
    hopStrip || insights.length || questions.length || refs.length
      ? chainComplete
        ? `[citation_chain] chain_complete=true · hops: ${hopStrip}`
        : `[citation_chain] chain_complete=false · hops: ${hopStrip || "(incomplete)"}`
      : "",
    ...insights.map((i, idx) => `[insight] [evidence-insight-${idx}] ${i}`),
    ...questions.map((q, idx) => `[question] [evidence-question-${idx}] ${q}`),
    ...refs.map((r, idx) => `[ref] [evidence-source-${idx}] ${r}`),
  ].filter(Boolean);
  const plainFromHtml = plainTextFromHtml(opts.html || "");
  const plain =
    plainParts.join("\n") + (plainFromHtml ? `\n\n${plainFromHtml}` : "");
  if (!plain.trim()) return null;
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const spawn = String(opts.spawnId || "").trim();
  const tier = String(opts.researchTier || "").trim();
  const bodyHtml =
    String(opts.html || "").trim() ||
    `<ul class="insights">${insights.map((i) => `<li>${escape(i)}</li>`).join("")}</ul>` +
      `<ul class="questions">${questions.map((q) => `<li>${escape(q)}</li>`).join("")}</ul>` +
      (refs.length
        ? `<ul class="refs">${refs.map((r) => `<li>${escape(r)}</li>`).join("")}</ul>`
        : "");
  const html =
    `<article data-view-format="html" data-source="evidence_pack" data-asset-id="${escape(asset)}"` +
    (spawn ? ` data-spawn-id="${escape(spawn)}"` : "") +
    ` data-ref-count="${refs.length}"` +
    ` data-chain-complete="${chainComplete ? "true" : "false"}"` +
    (hopStrip ? ` data-citation-chain-hops="${escape(hopStrip)}"` : "") +
    `>` +
    `<h1>Evidence pack · ${escape(asset)}</h1>` +
    (tier ? `<p class="tier"><strong>tier:</strong> ${escape(tier)}</p>` : "") +
    (hopStrip
      ? `<p class="citation-chain-hops">Citation chain hops: ${escape(hopStrip)}</p>`
      : "") +
    bodyHtml +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Evidence pack · ${asset}`,
    asset_id: asset,
    note_ids: [],
    source: "evidence_pack",
    // Residual (aei): evidence body required for seed → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (rc): Write handoff from publication hydrate (arxiv/substack/url).
 * twin_seed only — knowledge-dense pubs seed writing without inventing docs.
 */
export function buildPublicationHydrateWriteHref(opts: {
  spawnId?: string | null;
  assets: ReadonlyArray<{
    asset_id?: string | null;
    title?: string | null;
    body_text?: string | null;
    html?: string | null;
    offline_honest?: boolean | null;
    fetched?: boolean | null;
    ref?: {
      kind?: string | null;
      raw?: string | null;
      canonical_url?: string | null;
      title_hint?: string | null;
    } | null;
  }>;
}): string | null {
  const assets = opts.assets || [];
  if (!assets.length) return null;
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const lines: string[] = [];
  const sections: string[] = [];
  for (const a of assets) {
    const id = String(a.asset_id || "").trim() || "pub";
    const title = String(a.title || a.ref?.title_hint || a.ref?.raw || id).trim();
    const body = String(a.body_text || "").trim() || plainTextFromHtml(a.html || "");
    const kind = String(a.ref?.kind || "").trim();
    const raw = String(a.ref?.raw || "").trim();
    const url = String(a.ref?.canonical_url || "").trim();
    lines.push(
      [
        `[pub] ${title}`,
        kind ? `kind=${kind}` : "",
        raw ? `raw=${raw}` : "",
        url ? url : "",
        body ? body.slice(0, 1200) : "",
      ]
        .filter(Boolean)
        .join(" · "),
    );
    sections.push(
      `<section data-asset-id="${escape(id)}">` +
        `<h2>${escape(title)}</h2>` +
        (kind || raw
          ? `<p class="ref">${escape([kind, raw, url].filter(Boolean).join(" · "))}</p>`
          : "") +
        (String(a.html || "").trim()
          ? String(a.html)
          : body
            ? `<pre>${escape(body.slice(0, 4000))}</pre>`
            : "") +
        `</section>`,
    );
  }
  const plain = lines.join("\n\n");
  if (!plain.trim()) return null;
  const spawn = String(opts.spawnId || "").trim();
  const firstId = String(assets[0]?.asset_id || "").trim() || "publication";
  const html =
    `<article data-view-format="html" data-source="publication_hydrate"` +
    (spawn ? ` data-spawn-id="${escape(spawn)}"` : "") +
    ` data-pub-count="${assets.length}">` +
    `<h1>Publications · ${escape(spawn || firstId)}</h1>` +
    sections.join("") +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Publications · ${spawn || firstId}`,
    asset_id: firstId,
    note_ids: [],
    source: "publication_hydrate",
    // Residual (aei): hydrated pub plain required for seed → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (re): Write handoff after session flywheel complete.
 * twin_seed only — output + prompt block seed recursive note-taker Write path.
 */
export function buildSessionFlywheelWriteHref(opts: {
  sessionId: string;
  spawnId?: string | null;
  outputText?: string | null;
  promptBlock?: string | null;
  status?: string | null;
  researchTier?: string | null;
}): string | null {
  const session = String(opts.sessionId || "").trim();
  const output = String(opts.outputText || "").trim();
  const prompt = String(opts.promptBlock || "").trim();
  if (!session) return null;
  if (!output && !prompt) return null;
  const spawn = String(opts.spawnId || "").trim();
  const status = String(opts.status || "").trim();
  const tier = String(opts.researchTier || "").trim();
  const plain = [
    `Session: ${session}`,
    spawn ? `Spawn: ${spawn}` : "",
    status ? `Status: ${status}` : "",
    tier ? `Tier: ${tier}` : "",
    output ? `Output:\n${output}` : "",
    prompt ? `Prompt block:\n${prompt}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const html =
    `<article data-view-format="html" data-source="session_flywheel_complete" data-session-id="${escape(session)}"` +
    (spawn ? ` data-spawn-id="${escape(spawn)}"` : "") +
    `>` +
    `<h1>Session complete · ${escape(session)}</h1>` +
    (status ? `<p class="status"><strong>Status:</strong> ${escape(status)}</p>` : "") +
    (tier ? `<p class="tier"><strong>Tier:</strong> ${escape(tier)}</p>` : "") +
    (output ? `<section class="output"><h2>Output</h2><pre>${escape(output)}</pre></section>` : "") +
    (prompt ? `<section class="prompt"><h2>Prompt block</h2><pre>${escape(prompt)}</pre></section>` : "") +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Session complete · ${session}`,
    asset_id: spawn ? `deep_research:${spawn}` : `session:${session}`,
    note_ids: [],
    source: "session_flywheel_complete",
    // Residual (aei): flywheel output/prompt required for seed → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (rf): Write handoff from intelligent context search hits.
 * twin_seed only — search substrate seeds writing without inventing docs.
 */
export function buildContextSearchWriteHref(opts: {
  assetId: string;
  query?: string | null;
  hits?: ReadonlyArray<{
    kind?: string | null;
    id?: string | null;
    text?: string | null;
  } | null | undefined>;
  html?: string | null;
  researchTier?: string | null;
}): string | null {
  const asset = String(opts.assetId || "").trim();
  if (!asset) return null;
  const query = String(opts.query || "").trim();
  const hits = (opts.hits || [])
    .map((h) => {
      if (!h) return "";
      const kind = String(h.kind || "").trim();
      const text = String(h.text || "").trim();
      if (!text) return "";
      return kind ? `[${kind}] ${text}` : text;
    })
    .filter(Boolean);
  const plainFromHtml = plainTextFromHtml(opts.html || "");
  const plain = [
    query ? `Query: ${query}` : "",
    ...hits,
    plainFromHtml,
  ]
    .filter(Boolean)
    .join("\n\n");
  if (!plain.trim()) return null;
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const tier = String(opts.researchTier || "").trim();
  const bodyHtml =
    String(opts.html || "").trim() ||
    `<ul class="hits">${hits.map((h) => `<li>${escape(h)}</li>`).join("")}</ul>`;
  const html =
    `<article data-view-format="html" data-source="context_search" data-asset-id="${escape(asset)}"` +
    (query ? ` data-query="${escape(query)}"` : "") +
    ` data-hit-count="${hits.length}">` +
    `<h1>Context search · ${escape(asset)}</h1>` +
    (query ? `<p class="query"><strong>Query:</strong> ${escape(query)}</p>` : "") +
    (tier ? `<p class="tier"><strong>Tier:</strong> ${escape(tier)}</p>` : "") +
    bodyHtml +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: query ? `Search · ${query}` : `Context search · ${asset}`,
    asset_id: asset,
    note_ids: [],
    source: "context_search",
    // Residual (aei): search hits required for seed → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (ri): Write handoff from research context prompt_block.
 * twin_seed only — the recursive context pack that drives prompts becomes writing seed.
 */
export function buildResearchContextWriteHref(opts: {
  assetId: string;
  spawnId?: string | null;
  promptBlock?: string | null;
  query?: string | null;
  researchTier?: string | null;
  twinCount?: number | null;
  refCount?: number | null;
}): string | null {
  const asset = String(opts.assetId || "").trim();
  const block = String(opts.promptBlock || "").trim();
  if (!asset || !block) return null;
  const spawn = String(opts.spawnId || "").trim();
  const query = String(opts.query || "").trim();
  const tier = String(opts.researchTier || "").trim();
  const twins = typeof opts.twinCount === "number" ? opts.twinCount : null;
  const refs = typeof opts.refCount === "number" ? opts.refCount : null;
  const plain = [
    `Asset: ${asset}`,
    spawn ? `Spawn: ${spawn}` : "",
    query ? `Query: ${query}` : "",
    tier ? `Tier: ${tier}` : "",
    twins != null ? `Twins: ${twins}` : "",
    refs != null ? `Refs: ${refs}` : "",
    `Prompt block:\n${block}`,
  ]
    .filter(Boolean)
    .join("\n\n");
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const html =
    `<article data-view-format="html" data-source="research_context_pack" data-asset-id="${escape(asset)}"` +
    (spawn ? ` data-spawn-id="${escape(spawn)}"` : "") +
    `>` +
    `<h1>Research context · ${escape(asset)}</h1>` +
    (query ? `<p class="query"><strong>Query:</strong> ${escape(query)}</p>` : "") +
    (tier ? `<p class="tier"><strong>Tier:</strong> ${escape(tier)}</p>` : "") +
    `<section class="prompt-block"><h2>Prompt block</h2><pre>${escape(block)}</pre></section>` +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Research context · ${asset}`,
    asset_id: asset,
    note_ids: [],
    source: "research_context_pack",
    // Residual (aei): prompt_block required for seed → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

/**
 * Residual (rr): Write handoff after twin promote → context.
 * twin_seed only — promoted recursive note-taker units seed writing.
 */
export function buildTwinPromoteWriteHref(opts: {
  assetId: string;
  query?: string | null;
  contextUnits?: ReadonlyArray<{
    kind?: string | null;
    text?: string | null;
    unit_id?: string | null;
    twin_note_id?: string | null;
  } | null | undefined>;
  noteIds?: ReadonlyArray<string | null | undefined> | null;
  html?: string | null;
  promotedCount?: number | null;
}): string | null {
  const asset = String(opts.assetId || "").trim();
  if (!asset) return null;
  const units = (opts.contextUnits || [])
    .map((u) => {
      if (!u) return "";
      const kind = String(u.kind || "").trim();
      const text = String(u.text || "").trim();
      if (!text) return "";
      return kind ? `[${kind}] ${text}` : text;
    })
    .filter(Boolean);
  const plainFromHtml = plainTextFromHtml(opts.html || "");
  const query = String(opts.query || "").trim();
  const n = typeof opts.promotedCount === "number" ? opts.promotedCount : units.length;
  const noteIds = (opts.noteIds || [])
    .map((x) => String(x || "").trim())
    .filter(Boolean);
  const plain = [
    query ? `Query: ${query}` : "",
    n > 0 ? `Promoted units: ${n}` : "",
    noteIds.length ? `note_ids: ${noteIds.join(",")}` : "",
    ...units,
    plainFromHtml,
  ]
    .filter(Boolean)
    .join("\n\n");
  if (!plain.trim()) return null;
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const bodyHtml =
    String(opts.html || "").trim() ||
    `<ul class="context-units">${units.map((u) => `<li>${escape(u)}</li>`).join("")}</ul>`;
  const html =
    `<article data-view-format="html" data-source="twin_promote_context" data-asset-id="${escape(asset)}"` +
    ` data-promoted-count="${n}">` +
    `<h1>Twin promote · ${escape(asset)}</h1>` +
    (query ? `<p class="query"><strong>Query:</strong> ${escape(query)}</p>` : "") +
    bodyHtml +
    `</article>`;
  const seedKey = storeTwinWriteSeed({
    plain_text: plain,
    html,
    title: `Twin promote · ${asset}`,
    asset_id: asset,
    note_ids: noteIds,
    source: "twin_promote_context",
    // Residual (aei): promoted notes plain required for seed → has_body true.
    has_body: true,
  });
  if (!seedKey) return null;
  return buildTwinWriteHref(seedKey);
}

