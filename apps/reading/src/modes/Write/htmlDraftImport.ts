/**
 * htmlDraftImport — pure helpers for landing hosted HTML research drafts
 * into Write mode (residuals fl/fm/ft/fu).
 *
 * HTML-first only: refuse non-html view_format. Does not invent body text.
 * Residual (fu): split h1–h3 structure into outline sections for multi-section land.
 */

export type HtmlDraftImportInput = {
  document_id: string;
  view_format?: string | null;
  html?: string | null;
  title?: string | null;
};

export type HtmlDraftImportPrepared = {
  document_id: string;
  view_format: "html";
  title: string;
  html: string;
  plain_text: string;
  plain_preview: string;
  title_hint: string;
  /** Residual (fu): outline sections derived from HTML headings (or single body). */
  outline_sections: OutlineSectionImport[];
};

/** One outline section candidate for createSection + updateSectionProse. */
export type OutlineSectionImport = {
  title: string;
  plain_text: string;
  section_index: number;
  /**
   * Residual (fv): heading level 1–3 for nesting under parent_section_id.
   * 0 = preamble / single-body fallback (top-level).
   */
  heading_level: number;
  /**
   * Residual (fx): raw HTML fragment for the section body (HTML-first prose).
   * Empty when only plain fallback is available.
   */
  html_fragment: string;
};

/** Max sections created on import (hard-to-vary safety cap). */
export const MAX_OUTLINE_SECTIONS = 20;

/** Strip tags / collapse whitespace for brainstorm / title hints. */
export function stripHtmlToPlainText(html: string): string {
  const withoutTags = (html || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
  return withoutTags.replace(/\s+/g, " ").trim();
}

/** Prefer API title; else first non-empty plain sentence/line (≤120 chars). */
export function titleHintFromDraft(opts: {
  title?: string | null;
  plain_text?: string | null;
  document_id?: string | null;
}): string {
  const t = (opts.title || "").trim();
  if (t) return t.slice(0, 120);
  const plain = (opts.plain_text || "").trim();
  if (plain) {
    const first = plain.split(/(?<=[.!?])\s+/)[0] || plain;
    return first.slice(0, 120);
  }
  const id = (opts.document_id || "").trim();
  return id ? `Draft from ${id.slice(0, 80)}` : "HTML research draft";
}

/**
 * Residual (fu): split HTML on h1–h3 into outline sections.
 * Preamble before the first heading becomes "Introduction" (or fallbackTitle)
 * when non-empty. No headings → single section with fallbackTitle.
 * Empty bodies after a heading keep the heading text as minimal prose.
 * Capped at MAX_OUTLINE_SECTIONS.
 */
export function splitHtmlIntoOutlineSections(
  html: string,
  fallbackTitle: string,
): OutlineSectionImport[] {
  const cleaned = (html || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "");
  const re = /<h([1-3])\b[^>]*>([\s\S]*?)<\/h\1>/gi;
  const matches = Array.from(cleaned.matchAll(re));
  const fallback = (fallbackTitle || "Imported HTML draft").trim().slice(0, 120);

  if (matches.length === 0) {
    const plain = stripHtmlToPlainText(cleaned);
    if (!plain) return [];
    const frag = cleaned.trim().slice(0, 100_000);
    return [
      {
        title: fallback || "Imported HTML draft",
        plain_text: plain.slice(0, 100_000),
        section_index: 0,
        heading_level: 0,
        html_fragment: frag,
      },
    ];
  }

  const sections: OutlineSectionImport[] = [];
  const firstIdx = matches[0].index ?? 0;
  if (firstIdx > 0) {
    const preamble = cleaned.slice(0, firstIdx);
    const plain = stripHtmlToPlainText(preamble);
    if (plain) {
      sections.push({
        title: (fallback || "Introduction").slice(0, 120),
        plain_text: plain.slice(0, 100_000),
        section_index: 0,
        heading_level: 0,
        html_fragment: preamble.trim().slice(0, 100_000),
      });
    }
  }

  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const level = Math.min(3, Math.max(1, parseInt(m[1] || "1", 10) || 1));
    const headingPlain = stripHtmlToPlainText(m[2] || "");
    const title =
      headingPlain.slice(0, 120) || `Section ${sections.length + 1}`;
    const start = (m.index ?? 0) + m[0].length;
    const end =
      i + 1 < matches.length
        ? (matches[i + 1].index ?? cleaned.length)
        : cleaned.length;
    const bodyHtml = cleaned.slice(start, end).trim();
    const bodyPlain = stripHtmlToPlainText(bodyHtml);
    const plain_text = (bodyPlain || headingPlain || title).slice(0, 100_000);
    if (!plain_text.trim()) continue;
    // Residual (fx): keep HTML body when present; wrap heading if body empty.
    const html_fragment = (
      bodyHtml ||
      (headingPlain ? `<p>${escapeHtmlText(headingPlain)}</p>` : "")
    ).slice(0, 100_000);
    sections.push({
      title,
      plain_text,
      section_index: sections.length,
      heading_level: level,
      html_fragment,
    });
  }

  return sections.slice(0, MAX_OUTLINE_SECTIONS).map((s, i) => ({
    ...s,
    section_index: i,
  }));
}

/** Minimal escape for heading-only HTML fallback fragments. */
function escapeHtmlText(s: string): string {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Prepare a hosted document response for Write handoff.
 * Throws if view_format is not html or html body is empty.
 */
export function prepareHtmlDraftForWrite(
  input: HtmlDraftImportInput,
): HtmlDraftImportPrepared {
  const document_id = (input.document_id || "").trim();
  if (!document_id) {
    throw new Error("document_id is required");
  }
  const view = (input.view_format || "html").trim().toLowerCase();
  if (view !== "html") {
    throw new Error("view_format must be html — PDF is not a valid write surface");
  }
  const html = (input.html || "").trim();
  if (!html) {
    throw new Error("html body is empty");
  }
  const plain_text = stripHtmlToPlainText(html);
  const title_hint = titleHintFromDraft({
    title: input.title,
    plain_text,
    document_id,
  });
  const title = (input.title || "").trim() || title_hint;
  const outline_sections = splitHtmlIntoOutlineSections(html, title_hint);
  return {
    document_id,
    view_format: "html",
    title,
    html,
    plain_text,
    plain_preview: plain_text.slice(0, 600) + (plain_text.length > 600 ? "…" : ""),
    title_hint,
    outline_sections,
  };
}
