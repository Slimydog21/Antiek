/**
 * HTML-native source attach compose (pure).
 *
 * Operator vision: call arxiv, substack, and other knowledge-dense
 * publications into deep research / wrestle sessions — every information
 * asset viewed as HTML. This pure layer attaches operator-supplied HTML
 * source refs to a session without remote fetch or PDF authority.
 *
 * remote_fetched always false.
 * pdf_view_authorized always false (HTML-native doctrine).
 * store_mutated always false.
 */

import {
  DEFAULT_PUBLICATION_CATALOG,
  selectPublicationSources,
  type PublicationFamily,
  type SourceSelectionPack,
} from "./sourcePublicationRegistry";

export type AttachSourceFamily = PublicationFamily;

export interface HtmlNativeSourceRef {
  source_id: string;
  family: AttachSourceFamily;
  /** Operator-supplied title — never invented. */
  title: string;
  /** Optional external id (arxiv:…, substack slug). */
  external_id?: string;
  /** Optional canonical URL (caller-supplied). */
  url?: string;
  /**
   * Optional HTML fragment already hosted / projected for this source.
   * When absent, attach is still proposed but html_ready=false for that ref.
   */
  html_fragment?: string;
}

export interface HtmlNativeSourceAttachInput {
  session_id: string;
  parent_asset_id: string;
  requested_families: AttachSourceFamily[];
  sources: HtmlNativeSourceRef[];
  /** Operator ack that these sources may inform the research pack. */
  operator_ack: boolean;
}

export interface HtmlNativeSourceAttachCompose {
  session_id: string;
  parent_asset_id: string;
  selection: SourceSelectionPack;
  source_ids: string[];
  source_count: number;
  /** Count of sources that carry caller-supplied HTML fragments. */
  html_ready_count: number;
  /** True when ≥1 source, selection non-empty, operator_ack. */
  attach_ready: boolean;
  /** Always false — pure layer never remote-fetches publications. */
  remote_fetched: false;
  /** Always false — PDF view not authorized; HTML-native only. */
  pdf_view_authorized: false;
  /** Always false — no asset store mutation. */
  store_mutated: false;
  notes: string[];
  authority: "html_native_source_attach_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

const VALID_FAMILIES = new Set<AttachSourceFamily>([
  "arxiv",
  "substack",
  "openalex",
  "web",
  "custom",
]);

/**
 * Attach HTML-native source refs to a research/wrestle session.
 * Never fetches remote; never authorizes PDF; never mutates store.
 */
export function composeHtmlNativeSourceAttach(
  input: HtmlNativeSourceAttachInput,
): HtmlNativeSourceAttachCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (
    !Array.isArray(input.requested_families) ||
    input.requested_families.length === 0
  ) {
    throw new Error("requested_families must be a non-empty array");
  }
  if (!Array.isArray(input.sources)) {
    throw new Error("sources must be an array");
  }

  const notes: string[] = [
    "remote_fetched=false — no live arxiv/substack fetch in pure layer",
    "pdf_view_authorized=false — HTML-native doctrine",
    "store_mutated=false — attach is advisory pack only",
  ];

  for (const f of input.requested_families) {
    if (!VALID_FAMILIES.has(f)) {
      throw new Error(`requested_families contains invalid family: ${f}`);
    }
  }

  const selection = selectPublicationSources(
    { requested_families: input.requested_families, enabled_only: true },
    DEFAULT_PUBLICATION_CATALOG,
  );
  notes.push(`selection families=${selection.families.length}`);

  const source_ids: string[] = [];
  const seen = new Set<string>();
  let html_ready_count = 0;

  for (let i = 0; i < input.sources.length; i++) {
    const s = input.sources[i];
    if (!s || typeof s !== "object") {
      throw new Error(`sources[${i}] must be an object`);
    }
    const id = requireNonEmpty(s.source_id, `sources[${i}].source_id`);
    if (seen.has(id)) {
      throw new Error(`duplicate source_id: ${id}`);
    }
    seen.add(id);
    if (!VALID_FAMILIES.has(s.family)) {
      throw new Error(`sources[${i}].family invalid`);
    }
    if (!input.requested_families.includes(s.family)) {
      throw new Error(
        `sources[${i}].family ${s.family} not in requested_families`,
      );
    }
    requireNonEmpty(s.title, `sources[${i}].title`);
    if (s.external_id != null) {
      requireNonEmpty(s.external_id, `sources[${i}].external_id`);
    }
    if (s.url != null) {
      requireNonEmpty(s.url, `sources[${i}].url`);
    }
    if (s.html_fragment != null) {
      if (typeof s.html_fragment !== "string" || !s.html_fragment.trim()) {
        throw new Error(
          `sources[${i}].html_fragment must be non-empty string when set`,
        );
      }
      html_ready_count += 1;
    }
    source_ids.push(id);
  }

  const source_count = source_ids.length;
  notes.push(
    `source_count=${source_count} · html_ready_count=${html_ready_count}`,
  );

  const attach_ready =
    input.operator_ack &&
    source_count >= 1 &&
    input.requested_families.length >= 1;

  if (!input.operator_ack) {
    notes.push("attach_ready=false — operator_ack required");
  } else if (source_count === 0) {
    notes.push("attach_ready=false — no sources (no invent)");
  } else {
    notes.push(
      html_ready_count === source_count
        ? "attach_ready=true · all sources have HTML fragments"
        : `attach_ready=true · ${html_ready_count}/${source_count} sources have HTML (rest proposed without body)`,
    );
  }

  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    selection,
    source_ids,
    source_count,
    html_ready_count,
    attach_ready,
    remote_fetched: false,
    pdf_view_authorized: false,
    store_mutated: false,
    notes,
    authority: "html_native_source_attach_compose_advisory",
  };
}

export function formatHtmlNativeSourceAttachSummary(
  c: HtmlNativeSourceAttachCompose,
): string {
  return (
    `attach_ready=${c.attach_ready} · sources=${c.source_count} · ` +
    `html_ready=${c.html_ready_count} · remote_fetched=false · pdf_view_authorized=false`
  );
}
