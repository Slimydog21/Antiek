/**
 * Residual (aup): pure spawn-merge HTML open readiness.
 *
 * After draft/parent merge, float|full|Write open requires view_format=html ·
 * non-empty body · document_id. Never invents open when PDF / empty / missing id.
 *
 * Parity marketplaceHostedOpenReadiness (atm) · moilDepositHtmlReadiness (ate).
 * Source provenance: spawn_merge (write-seed / Antiek-bench feed).
 */

export type SpawnMergeHtmlOpenReadiness = {
  view_format_html: boolean;
  has_html_body: boolean;
  has_document_id: boolean;
  open_ready: boolean;
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  source: "spawn_merge";
  merge_mode: string;
  summary: string;
  open_title: string;
};

/**
 * Merged research HTML open path readiness from merge product fields.
 * open_ready only when HTML view + body + document_id are present.
 */
export function spawnMergeHtmlOpenReadiness(opts: {
  view_format?: string | null;
  html?: string | null;
  document_id?: string | null;
  mode?: string | null;
}): SpawnMergeHtmlOpenReadiness {
  const view_format_html =
    String(opts.view_format || "")
      .trim()
      .toLowerCase() === "html";
  const has_html_body = Boolean(String(opts.html || "").trim());
  const has_document_id = Boolean(String(opts.document_id || "").trim());
  const merge_mode = String(opts.mode || "").trim() || "unknown";
  const open_ready = view_format_html && has_html_body && has_document_id;

  let summary: string;
  let open_title: string;
  if (open_ready) {
    summary = `html merge ready · mode=${merge_mode} · open float|full|Write`;
    open_title =
      "Open merged research as HTML reading window (highlight→DR→merge · twin seed path · never PDF)";
  } else if (!view_format_html) {
    summary = "view_format must be html (never PDF open)";
    open_title =
      "Merged view_format must be html — PDF is not a reading surface";
  } else if (!has_html_body) {
    summary = "merged HTML body empty";
    open_title = "Merged HTML body empty — cannot open reading window";
  } else {
    summary = "merged document_id missing";
    open_title = "Merged document_id missing — cannot open reading window";
  }

  return {
    view_format_html,
    has_html_body,
    has_document_id,
    open_ready,
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    source: "spawn_merge",
    merge_mode,
    summary,
    open_title,
  };
}
