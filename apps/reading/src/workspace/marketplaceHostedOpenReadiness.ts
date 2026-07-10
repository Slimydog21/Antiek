/**
 * Residual (atm): pure marketplace hosted HTML open readiness.
 *
 * Open hosted book in reading window requires view_format=html · non-empty
 * body · document_id. Never invents open when PDF / empty / missing id.
 * Parity moilDepositHtmlReadiness (ate) for marketplace account-hosted path.
 */

export type MarketplaceHostedOpenReadiness = {
  view_format_html: boolean;
  has_html_body: boolean;
  has_document_id: boolean;
  open_ready: boolean;
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  summary: string;
  open_title: string;
};

/**
 * Hosted book open path readiness from land result fields.
 * open_ready only when HTML view + body + document_id are present.
 */
export function marketplaceHostedOpenReadiness(opts: {
  view_format?: string | null;
  html?: string | null;
  document_id?: string | null;
}): MarketplaceHostedOpenReadiness {
  const view_format_html =
    String(opts.view_format || "")
      .trim()
      .toLowerCase() === "html";
  const has_html_body = Boolean(String(opts.html || "").trim());
  const has_document_id = Boolean(String(opts.document_id || "").trim());
  const open_ready = view_format_html && has_html_body && has_document_id;

  let summary: string;
  let open_title: string;
  if (open_ready) {
    summary = "html hosted book ready · open reading window";
    open_title =
      "Open hosted book as HTML reading window (seamless account port · twin seed path · never PDF)";
  } else if (!view_format_html) {
    summary = "view_format must be html (never PDF open)";
    open_title =
      "Hosted view_format must be html — PDF is not a reading surface";
  } else if (!has_html_body) {
    summary = "hosted HTML body empty";
    open_title = "Hosted HTML body empty — cannot open reading window";
  } else {
    summary = "hosted document_id missing";
    open_title = "Hosted document_id missing — cannot open reading window";
  }

  return {
    view_format_html,
    has_html_body,
    has_document_id,
    open_ready,
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    summary,
    open_title,
  };
}
