/**
 * HTML-native view session authority pack (pure).
 *
 * Operator vision: every information asset viewed as HTML — reading and
 * research share the same authority doctrine; open a session only when HTML
 * projection is ready; PDF never primary.
 *
 * pdf_view_authorized always false.
 * pdf_primary always false.
 * store_mutated always false.
 */

import {
  composeHtmlAssetViewSession,
  type HtmlAssetViewSessionCompose,
} from "./htmlAssetViewSessionCompose";
import {
  composeReadingResearchHtmlParity,
  type ModeAssetViewInput,
  type ReadingResearchHtmlParityCompose,
} from "./readingResearchHtmlParityCompose";
import {
  evaluateHtmlNativeViewAuthority,
  type HtmlNativeViewAuthorityDecision,
} from "./htmlNativeViewAuthority";

export interface HtmlNativeViewSessionAuthorityInput {
  session_id: string;
  /** Primary asset for the open session. */
  asset_id: string;
  html_projection_sha: string | null;
  view_requested: boolean;
  twin_bound: boolean;
  twin_substrate_ready?: boolean;
  claimed_format?: string | null;
  /**
   * Reading/research parity surface inputs. When omitted, both modes use
   * the primary asset with source_format derived from claimed_format.
   */
  reading?: ModeAssetViewInput | null;
  research?: ModeAssetViewInput | null;
  operator_ack: boolean;
}

export interface HtmlNativeViewSessionAuthorityCompose {
  session_id: string;
  asset_id: string;
  session: HtmlAssetViewSessionCompose;
  authority: HtmlNativeViewAuthorityDecision;
  parity: ReadingResearchHtmlParityCompose;
  /**
   * True when session.session_ready, authority.human_viewable_html,
   * parity.parity_ready (or both unavailable honesty), and operator_ack.
   */
  pack_ready: boolean;
  pdf_view_authorized: false;
  pdf_primary: false;
  store_mutated: false;
  notes: string[];
  pack_authority: "html_native_view_session_authority_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveFormat(
  claimed: string | null | undefined,
): ModeAssetViewInput["source_format"] {
  if (claimed == null || claimed === undefined || !String(claimed).trim()) {
    return "unknown";
  }
  const f = String(claimed).trim().toLowerCase();
  if (f === "html" || f === "pdf" || f === "epub" || f === "markdown") {
    return f;
  }
  return "unknown";
}

/**
 * Compose HTML asset session + authority + reading/research parity.
 * Never authorizes PDF primary; never mutates store.
 */
export function composeHtmlNativeViewSessionAuthority(
  input: HtmlNativeViewSessionAuthorityInput,
): HtmlNativeViewSessionAuthorityCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");

  const notes: string[] = [
    "pdf_view_authorized=false — HTML-native doctrine",
    "pdf_primary=false",
    "store_mutated=false",
  ];

  const session = composeHtmlAssetViewSession({
    session_id,
    asset_id,
    html_projection_sha: input.html_projection_sha,
    view_requested: input.view_requested,
    twin_bound: input.twin_bound,
    twin_substrate_ready: input.twin_substrate_ready,
    claimed_format: input.claimed_format,
  });
  notes.push(...session.notes.map((n) => `[session] ${n}`));

  const source_format = deriveFormat(input.claimed_format);
  const authority = evaluateHtmlNativeViewAuthority({
    asset_id,
    asset_kind: "research",
    source_format,
    html_projection_sha: input.html_projection_sha,
    prefer_html: true,
    allow_pdf_secondary: false,
  });
  notes.push(...authority.notes.map((n) => `[authority] ${n}`));

  const reading: ModeAssetViewInput =
    input.reading != null
      ? input.reading
      : {
          asset_id,
          asset_kind: "book",
          source_format,
          html_projection_sha: input.html_projection_sha,
          prefer_html: true,
          allow_pdf_secondary: false,
        };
  const research: ModeAssetViewInput =
    input.research != null
      ? input.research
      : {
          asset_id,
          asset_kind: "research",
          source_format,
          html_projection_sha: input.html_projection_sha,
          prefer_html: true,
          allow_pdf_secondary: false,
        };

  const parity = composeReadingResearchHtmlParity({ reading, research });
  notes.push(...parity.notes.map((n) => `[parity] ${n}`));

  const pack_ready =
    session.session_ready === true &&
    authority.human_viewable_html === true &&
    parity.pdf_primary === false &&
    session.pdf_view_authorized === false &&
    input.operator_ack === true;

  if (pack_ready) {
    notes.push(
      "pack_ready=true — HTML view session + authority + parity ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — session, authority HTML, or operator_ack gate open",
    );
  }

  if (
    session.pdf_view_authorized !== false ||
    session.store_mutated !== false ||
    parity.pdf_primary !== false
  ) {
    throw new Error("invariant: PDF must never be authorized as primary view");
  }

  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    asset_id,
    session,
    authority,
    parity,
    pack_ready,
    pdf_view_authorized: false,
    pdf_primary: false,
    store_mutated: false,
    notes,
    pack_authority: "html_native_view_session_authority_compose_advisory",
  };
}

export function formatHtmlNativeViewSessionAuthoritySummary(
  c: HtmlNativeViewSessionAuthorityCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · session_ready=${c.session.session_ready} · ` +
    `human_viewable_html=${c.authority.human_viewable_html} · ` +
    `both_html_ready=${c.parity.both_html_ready} · ` +
    `pdf_view_authorized=false · pdf_primary=false · store_mutated=false`
  );
}
