/**
 * Residual (aty): pure intelligent context-search open readiness.
 *
 * Open float|full|Write from context search requires non-empty HTML body
 * (hits as HTML) · HTML-first · never PDF. Query honesty is surface chrome.
 * Parity marketplaceHostedOpenReadiness (atm) · moilDepositHtmlReadiness (ate).
 */

export type ContextSearchOpenReadiness = {
  has_html_body: boolean;
  has_query: boolean;
  hit_count: number;
  open_ready: boolean;
  write_ready: boolean;
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  source: "context_search";
  summary: string;
  open_title: string;
};

/**
 * Context search open path readiness from searchHits fields.
 * open_ready when HTML body present; write_ready when body or hit text present.
 */
export function contextSearchOpenReadiness(opts: {
  html?: string | null;
  query?: string | null;
  hit_count?: number | null;
  /** True when any hit has non-empty text (Write twin_seed body). */
  has_hit_text?: boolean | null;
}): ContextSearchOpenReadiness {
  const has_html_body = Boolean(String(opts.html || "").trim());
  const has_query = Boolean(String(opts.query || "").trim());
  const hit_count =
    typeof opts.hit_count === "number" && Number.isFinite(opts.hit_count)
      ? Math.max(0, Math.floor(opts.hit_count))
      : 0;
  const has_hit_text = Boolean(opts.has_hit_text);
  const open_ready = has_html_body;
  const write_ready = has_html_body || has_hit_text;

  let summary: string;
  let open_title: string;
  if (open_ready) {
    summary = "context search HTML ready · open float|full|Write";
    open_title =
      "Open search hits as HTML window (intelligent search · HTML-first · never PDF)";
  } else if (write_ready) {
    summary = "hit text present · Write ready · float/full need HTML";
    open_title =
      "Search HTML body empty — Open Write from hit text only (never invent HTML)";
  } else {
    summary = "context search HTML empty · no hit text";
    open_title =
      "Context search body empty — cannot open HTML reading window (never PDF)";
  }

  return {
    has_html_body,
    has_query,
    hit_count,
    open_ready,
    write_ready,
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    source: "context_search",
    summary,
    open_title,
  };
}
