/**
 * HTML-native view authority for any information asset (pure).
 *
 * Operator vision: every human-viewable information asset (books, research
 * output, twins) is viewed as HTML — not PDF as the primary surface.
 *
 * This pure layer decides whether HTML is the authorized human view path.
 * Never invents a ready HTML projection sha or hosted=true.
 */

export type AssetKind =
  | "book"
  | "research"
  | "twin"
  | "analysis"
  | "paper"
  | "other";

export type SourceFormat = "html" | "pdf" | "epub" | "markdown" | "unknown";

export interface HtmlNativeViewAuthorityInput {
  asset_id: string;
  asset_kind: AssetKind;
  source_format: SourceFormat;
  /**
   * Ready HTML projection content sha when known.
   * Null/blank means not ready — never invent.
   */
  html_projection_sha?: string | null;
  /** Explicit operator preference for HTML (default true for Antiek doctrine). */
  prefer_html?: boolean;
  /** If true, PDF may be offered as secondary download only. */
  allow_pdf_secondary?: boolean;
}

export interface HtmlNativeViewAuthorityDecision {
  asset_id: string;
  asset_kind: AssetKind;
  /** True only when prefer_html and a non-empty html_projection_sha is present. */
  human_viewable_html: boolean;
  /** PDF is never the primary human view path under HTML doctrine. */
  primary_format: "html" | "unavailable";
  pdf_secondary_allowed: boolean;
  html_projection_sha: string | null;
  notes: string[];
  authority: "html_native_view_authority_advisory";
}

const VALID_KINDS = new Set<AssetKind>([
  "book",
  "research",
  "twin",
  "analysis",
  "paper",
  "other",
]);

const VALID_FORMATS = new Set<SourceFormat>([
  "html",
  "pdf",
  "epub",
  "markdown",
  "unknown",
]);

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Decide HTML-native human view authority for an asset.
 * Never invents ready projection or hosted completion.
 */
export function evaluateHtmlNativeViewAuthority(
  input: HtmlNativeViewAuthorityInput,
): HtmlNativeViewAuthorityDecision {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");
  if (!VALID_KINDS.has(input.asset_kind)) {
    throw new Error(
      "asset_kind must be book|research|twin|analysis|paper|other",
    );
  }
  if (!VALID_FORMATS.has(input.source_format)) {
    throw new Error(
      "source_format must be html|pdf|epub|markdown|unknown",
    );
  }

  const prefer_html =
    input.prefer_html === undefined ? true : input.prefer_html;
  if (typeof prefer_html !== "boolean") {
    throw new Error("prefer_html must be an explicit boolean when set");
  }
  const allow_pdf_secondary =
    input.allow_pdf_secondary === undefined ? true : input.allow_pdf_secondary;
  if (typeof allow_pdf_secondary !== "boolean") {
    throw new Error("allow_pdf_secondary must be an explicit boolean when set");
  }

  const notes: string[] = [
    "HTML is the primary human-viewable surface (Antiek doctrine)",
    "PDF is never primary human view under this authority",
  ];

  let html_sha: string | null = null;
  if (input.html_projection_sha != null && input.html_projection_sha !== undefined) {
    if (typeof input.html_projection_sha !== "string") {
      throw new Error("html_projection_sha must be string or null");
    }
    const t = input.html_projection_sha.trim();
    html_sha = t || null;
  }

  if (input.source_format === "pdf") {
    notes.push("source is pdf — requires HTML projection before human primary view");
  }
  if (input.source_format === "html" && !html_sha) {
    notes.push(
      "source_format=html but html_projection_sha unknown — not inventing ready projection",
    );
  }

  let human_viewable_html = false;
  let primary_format: "html" | "unavailable" = "unavailable";

  if (!prefer_html) {
    notes.push("prefer_html=false — human_viewable_html=false (operator override)");
  } else if (!html_sha) {
    notes.push(
      "html_projection_sha missing — human_viewable_html=false (no invent ready)",
    );
  } else {
    human_viewable_html = true;
    primary_format = "html";
    notes.push(`HTML projection ready sha=${html_sha.slice(0, 16)}…`);
  }

  // Secondary PDF is only advisory allow; never primary.
  const pdf_secondary_allowed =
    allow_pdf_secondary &&
    (input.source_format === "pdf" || input.source_format === "epub");

  if (pdf_secondary_allowed && !human_viewable_html) {
    notes.push(
      "pdf/epub secondary download may be offered; primary human view still unavailable until HTML ready",
    );
  }

  return {
    asset_id,
    asset_kind: input.asset_kind,
    human_viewable_html,
    primary_format,
    pdf_secondary_allowed,
    html_projection_sha: html_sha,
    notes,
    authority: "html_native_view_authority_advisory",
  };
}

export function formatHtmlViewSummary(
  d: HtmlNativeViewAuthorityDecision,
): string {
  return (
    `asset=${d.asset_id} · primary=${d.primary_format} · ` +
    `human_viewable_html=${d.human_viewable_html}`
  );
}
