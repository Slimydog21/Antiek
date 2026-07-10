/**
 * Residual (aua): pure evidence-pack open readiness (citation trust).
 *
 * Open float|full|Write from evidence pack requires non-empty HTML body ·
 * HTML-first · never PDF. Citation trust grounded when ref_count > 0.
 * Parity contextSearchOpenReadiness · publicationHydrateOpenReadiness (aty).
 */

export type EvidencePackOpenReadiness = {
  has_html_body: boolean;
  ref_count: number;
  citation_trust: "grounded" | "ungrounded";
  open_ready: boolean;
  write_ready: boolean;
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  source: "evidence_pack";
  summary: string;
  open_title: string;
};

/**
 * Evidence pack open path readiness from pack fields.
 * open_ready when HTML body present; write_ready when insights/questions/HTML body.
 * citation_trust grounded only when ref_count > 0 (never invent sources).
 */
export function evidencePackOpenReadiness(opts: {
  html?: string | null;
  ref_count?: number | null;
  has_insight_text?: boolean | null;
  has_question_text?: boolean | null;
}): EvidencePackOpenReadiness {
  const has_html_body = Boolean(String(opts.html || "").trim());
  const ref_count =
    typeof opts.ref_count === "number" && Number.isFinite(opts.ref_count)
      ? Math.max(0, Math.floor(opts.ref_count))
      : 0;
  const citation_trust: "grounded" | "ungrounded" =
    ref_count > 0 ? "grounded" : "ungrounded";
  const has_twin_text = Boolean(opts.has_insight_text || opts.has_question_text);
  const open_ready = has_html_body;
  const write_ready = has_html_body || has_twin_text;

  let summary: string;
  let open_title: string;
  if (open_ready && citation_trust === "grounded") {
    summary = "grounded evidence HTML ready · open float|full|Write";
    open_title =
      "Open evidence pack as HTML window (citation trust grounded · multi-hop · never PDF)";
  } else if (open_ready) {
    summary = "ungrounded evidence HTML ready · open float|full|Write";
    open_title =
      "Open evidence pack as HTML window (citation trust ungrounded · multi-hop honest · never PDF)";
  } else if (write_ready) {
    summary = "twin text present · Write ready · float/full need HTML";
    open_title =
      "Evidence HTML empty — Open Write from insights/questions only (never invent HTML)";
  } else {
    summary = "evidence HTML empty · no twin text";
    open_title =
      "Evidence body empty — cannot open HTML reading window (never PDF)";
  }

  return {
    has_html_body,
    ref_count,
    citation_trust,
    open_ready,
    write_ready,
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    source: "evidence_pack",
    summary,
    open_title,
  };
}
