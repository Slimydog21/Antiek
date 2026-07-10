/**
 * Residual (aty): pure publication hydrate open readiness (arxiv/substack).
 *
 * Open float|full|Write from hydrate requires non-empty HTML body · HTML-first ·
 * never PDF. Offline-honest when no live injector body (dual-gate L1/L2).
 * Parity contextSearchOpenReadiness · marketplaceHostedOpenReadiness (atm).
 */

export type PublicationHydrateOpenReadiness = {
  has_html_body: boolean;
  has_document_id: boolean;
  fetched: boolean;
  offline_honest: boolean;
  open_ready: boolean;
  write_ready: boolean;
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  source: "publication_hydrate";
  summary: string;
  open_title: string;
};

/**
 * Publication hydrate open path readiness from hydrate result fields.
 * open_ready when HTML body present; write_ready when body_text or HTML present.
 * offline_honest when not fetched (identity path · dual-gate live deferred).
 */
export function publicationHydrateOpenReadiness(opts: {
  html?: string | null;
  body_text?: string | null;
  asset_id?: string | null;
  fetched?: boolean | null;
  offline_honest?: boolean | null;
}): PublicationHydrateOpenReadiness {
  const has_html_body = Boolean(String(opts.html || "").trim());
  const has_document_id = Boolean(String(opts.asset_id || "").trim());
  const has_body_text = Boolean(String(opts.body_text || "").trim());
  const fetched = Boolean(opts.fetched);
  // Parity ResearchContextPanel: offline_honest !== false && !fetched.
  const offline_honest = opts.offline_honest !== false && !fetched;
  const open_ready = has_html_body;
  const write_ready = has_html_body || has_body_text;

  let summary: string;
  let open_title: string;
  if (open_ready && offline_honest) {
    summary = "offline-honest hydrate HTML ready · open float|full|Write";
    open_title =
      "Open hydrated publication as HTML window (offline-honest identity · arxiv/substack · never PDF)";
  } else if (open_ready) {
    summary = "injector hydrate HTML ready · open float|full|Write";
    open_title =
      "Open hydrated publication as HTML window (injector landed · arxiv/substack · never PDF)";
  } else if (write_ready) {
    summary = "body_text present · Write ready · float/full need HTML";
    open_title =
      "Hydrate HTML empty — Open Write from body_text only (never invent HTML)";
  } else {
    summary = "hydrate HTML empty · no body_text";
    open_title =
      "Hydrate body empty — cannot open HTML reading window (never PDF)";
  }

  return {
    has_html_body,
    has_document_id,
    fetched,
    offline_honest,
    open_ready,
    write_ready,
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    source: "publication_hydrate",
    summary,
    open_title,
  };
}
