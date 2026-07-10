/**
 * Residual (asq): pure readiness for highlight → floating/full deep research launch.
 *
 * HTML reading engagement spine: document bound + HTML-first view → launch CTAs.
 * Optional highlight stamps from_highlight honesty; page/book-level launch still
 * allowed when document+HTML ready (never invent selection).
 * Offline-honest · never PDF view as launch surface.
 */

export type HighlightDrLaunchReadiness = {
  document_bound: boolean;
  view_format: "html" | "other";
  html_ready: boolean;
  has_highlight: boolean;
  /** True when document bound and HTML-first view (launch CTAs may fire). */
  launch_ready: boolean;
  /** Short operator-facing summary (no invented readiness). */
  summary: string;
};

/**
 * Compute highlight/book DR launch readiness for ResearchThis + HostedHtml.
 */
export function highlightDrLaunchReadiness(opts: {
  documentId?: string | null;
  /** Hosted view_format; ResearchThis is always html. */
  viewFormat?: string | null;
  highlightText?: string | null;
}): HighlightDrLaunchReadiness {
  const document_bound = Boolean(String(opts.documentId || "").trim());
  const vf = String(opts.viewFormat || "html")
    .trim()
    .toLowerCase();
  const view_format: "html" | "other" = vf === "html" || vf === "" ? "html" : "other";
  const html_ready = view_format === "html";
  const has_highlight = Boolean(String(opts.highlightText || "").trim());
  const launch_ready = document_bound && html_ready;

  let summary: string;
  if (!document_bound) {
    summary = "bind document for highlight → deep research launch · HTML-first";
  } else if (!html_ready) {
    summary = "view_format must be html · never PDF launch surface";
  } else if (has_highlight) {
    summary =
      "launch ready · highlight selection drives float|full DR · HTML-first · never PDF";
  } else {
    summary =
      "launch ready · book/page-level DR (no highlight) · HTML-first · never PDF";
  }

  return {
    document_bound,
    view_format,
    html_ready,
    has_highlight,
    launch_ready,
    summary,
  };
}
