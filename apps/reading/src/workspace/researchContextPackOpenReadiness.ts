/**
 * Residual (aub): pure research-context-pack open readiness.
 *
 * Open float|full|Write from research context pack requires non-empty
 * prompt_block body · HTML-first · never PDF. Twin/ref counts are honesty chrome.
 * Parity evidencePackOpenReadiness (aua) · contextSearchOpenReadiness (aty).
 */

export type ResearchContextPackOpenReadiness = {
  has_prompt_body: boolean;
  twin_count: number;
  ref_count: number;
  open_ready: boolean;
  write_ready: boolean;
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  source: "research_context_pack";
  summary: string;
  open_title: string;
};

/**
 * Research context pack open path readiness from pack fields.
 * open_ready / write_ready when prompt_block body is non-empty.
 */
export function researchContextPackOpenReadiness(opts: {
  prompt_block?: string | null;
  twin_count?: number | null;
  ref_count?: number | null;
}): ResearchContextPackOpenReadiness {
  const has_prompt_body = Boolean(String(opts.prompt_block || "").trim());
  const twin_count =
    typeof opts.twin_count === "number" && Number.isFinite(opts.twin_count)
      ? Math.max(0, Math.floor(opts.twin_count))
      : 0;
  const ref_count =
    typeof opts.ref_count === "number" && Number.isFinite(opts.ref_count)
      ? Math.max(0, Math.floor(opts.ref_count))
      : 0;
  const open_ready = has_prompt_body;
  const write_ready = has_prompt_body;

  let summary: string;
  let open_title: string;
  if (open_ready) {
    summary = "research context pack body ready · open float|full|Write";
    open_title =
      "Open research context pack as HTML window (recursive note-taker substrate · never PDF)";
  } else {
    summary = "research context pack prompt_block empty";
    open_title =
      "Context pack body empty — cannot open HTML reading window (never PDF)";
  }

  return {
    has_prompt_body,
    twin_count,
    ref_count,
    open_ready,
    write_ready,
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    source: "research_context_pack",
    summary,
    open_title,
  };
}
