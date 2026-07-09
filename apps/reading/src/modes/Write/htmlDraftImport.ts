/**
 * htmlDraftImport — pure helpers for landing hosted HTML research drafts
 * into Write mode (residuals fl/fm).
 *
 * HTML-first only: refuse non-html view_format. Does not invent body text.
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
};

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
  return {
    document_id,
    view_format: "html",
    title: (input.title || "").trim() || title_hint,
    html,
    plain_text,
    plain_preview: plain_text.slice(0, 600) + (plain_text.length > 600 ? "…" : ""),
    title_hint,
  };
}
