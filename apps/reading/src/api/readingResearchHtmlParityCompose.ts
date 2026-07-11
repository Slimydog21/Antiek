/**
 * Reading ↔ research HTML parity compose (pure).
 *
 * Operator vision: reading and research are the same at the view layer —
 * research consumes the HTML reading format. Both modes must authorize
 * human-viewable HTML with a real projection sha; PDF is never primary.
 *
 * pdf_primary is always false in this pure layer.
 */

import {
  evaluateHtmlNativeViewAuthority,
  type AssetKind,
  type HtmlNativeViewAuthorityDecision,
  type SourceFormat,
} from "./htmlNativeViewAuthority";

export interface ModeAssetViewInput {
  asset_id: string;
  asset_kind: AssetKind;
  source_format: SourceFormat;
  html_projection_sha?: string | null;
  prefer_html?: boolean;
  allow_pdf_secondary?: boolean;
}

export interface ReadingResearchHtmlParityCompose {
  reading: HtmlNativeViewAuthorityDecision;
  research: HtmlNativeViewAuthorityDecision;
  /** Both modes have human_viewable_html. */
  both_html_ready: boolean;
  /** Both modes share the same primary_format (html or unavailable). */
  primary_format_aligned: boolean;
  /**
   * True when both ready and same non-null projection sha, or both unavailable
   * without inventing sha equality.
   */
  parity_ready: boolean;
  /** Always false — PDF never primary under HTML doctrine. */
  pdf_primary: false;
  notes: string[];
  authority: "reading_research_html_parity_compose_advisory";
}

/**
 * Compose reading + research HTML view authority into a parity snapshot.
 * Never invents projection shas; never makes PDF primary.
 */
export function composeReadingResearchHtmlParity(input: {
  reading: ModeAssetViewInput;
  research: ModeAssetViewInput;
}): ReadingResearchHtmlParityCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (!input.reading || typeof input.reading !== "object") {
    throw new Error("reading must be an object");
  }
  if (!input.research || typeof input.research !== "object") {
    throw new Error("research must be an object");
  }

  const reading = evaluateHtmlNativeViewAuthority(input.reading);
  const research = evaluateHtmlNativeViewAuthority(input.research);
  const notes: string[] = [
    "pdf_primary=false — HTML doctrine; PDF never primary",
    "projection shas are caller-supplied only (no invent)",
  ];

  if (reading.primary_format === "html" && research.primary_format === "html") {
    notes.push("both modes primary_format=html");
  } else {
    notes.push(
      `primary_format reading=${reading.primary_format} research=${research.primary_format}`,
    );
  }

  const both_html_ready =
    reading.human_viewable_html && research.human_viewable_html;
  const primary_format_aligned =
    reading.primary_format === research.primary_format;

  let parity_ready = false;
  if (both_html_ready && primary_format_aligned) {
    const rSha = reading.html_projection_sha;
    const sSha = research.html_projection_sha;
    if (rSha && sSha && rSha === sSha) {
      parity_ready = true;
      notes.push("parity_ready=true — both HTML ready with matching projection sha");
    } else if (rSha && sSha && rSha !== sSha) {
      notes.push(
        "parity_ready=false — both HTML ready but projection sha differs (no invent merge)",
      );
    } else {
      notes.push(
        "parity_ready=false — human_viewable_html true without both non-empty shas",
      );
    }
  } else if (
    !reading.human_viewable_html &&
    !research.human_viewable_html &&
    primary_format_aligned
  ) {
    notes.push(
      "parity_ready=false — both unavailable (aligned but not viewable; no invent sha)",
    );
  } else {
    notes.push("parity_ready=false — modes not both HTML-ready or formats diverge");
  }

  notes.push("pdf_primary=false");

  return {
    reading,
    research,
    both_html_ready,
    primary_format_aligned,
    parity_ready,
    pdf_primary: false,
    notes,
    authority: "reading_research_html_parity_compose_advisory",
  };
}

export function formatReadingResearchHtmlParitySummary(
  c: ReadingResearchHtmlParityCompose,
): string {
  return (
    `html parity · ready=${c.parity_ready} · both_html=${c.both_html_ready} · ` +
    `aligned=${c.primary_format_aligned} · pdf_primary=false`
  );
}
