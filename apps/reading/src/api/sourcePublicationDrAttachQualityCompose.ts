/**
 * Source publication → HTML attach → citation → quality gate pack (pure).
 *
 * Operator vision: call arxiv, substack, and other knowledge-dense publications
 * into deep research as HTML-native refs with citation pack and quality/budget
 * gate — highest-quality DR readiness without live scrape/fetch.
 *
 * remote_fetched always false.
 * pdf_view_authorized always false.
 * store_mutated always false.
 * live_dispatch_authorized always false.
 */

import {
  composeHtmlNativeSourceAttach,
  type HtmlNativeSourceAttachCompose,
  type HtmlNativeSourceRef,
} from "./htmlNativeSourceAttachCompose";
import {
  buildDeepResearchSourceCitationPack,
  type CitationFamily,
  type CitationRecord,
  type DeepResearchSourceCitationPack,
} from "./deepResearchSourceCitationPack";
import {
  composeDeepResearchQualityBudgetGate,
  type DeepResearchQualityBudgetGateCompose,
} from "./deepResearchQualityBudgetGateCompose";
import type { PublicationFamily } from "./sourcePublicationRegistry";

export interface SourcePublicationDrAttachQualityInput {
  session_id: string;
  parent_asset_id: string;
  requested_families: PublicationFamily[];
  sources: HtmlNativeSourceRef[];
  /** Optional citation rows (caller-supplied). May be derived from sources. */
  citations?: CitationRecord[] | null;
  /** When true (default), build citations from sources if citations omitted. */
  derive_citations_from_sources?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  would_exceed: boolean | null;
  operator_override?: boolean;
  operator_ack: boolean;
}

export interface SourcePublicationDrAttachQualityCompose {
  session_id: string;
  parent_asset_id: string;
  attach: HtmlNativeSourceAttachCompose;
  citation_pack: DeepResearchSourceCitationPack;
  quality_gate: DeepResearchQualityBudgetGateCompose;
  /**
   * True when attach_ready + citation pack_ready + quality gate_ready.
   * Still never fetches or dispatches.
   */
  pack_ready: boolean;
  remote_fetched: false;
  pdf_view_authorized: false;
  store_mutated: false;
  live_dispatch_authorized: false;
  notes: string[];
  authority: "source_publication_dr_attach_quality_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveCitations(
  sources: HtmlNativeSourceRef[],
): CitationRecord[] {
  return sources.map((s, i) => ({
    citation_id: `cite-${s.source_id}`,
    family: s.family as CitationFamily,
    title: s.title,
    external_id: s.external_id,
    url: s.url,
  }));
}

/**
 * Compose arxiv/substack (etc.) HTML attach + citation pack + quality gate.
 * Never remote-fetches; never PDF; never live-dispatches.
 */
export function composeSourcePublicationDrAttachQuality(
  input: SourcePublicationDrAttachQualityInput,
): SourcePublicationDrAttachQualityCompose {
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

  const notes: string[] = [
    "remote_fetched=false — no live arxiv/substack scrape",
    "pdf_view_authorized=false — HTML-native only",
    "store_mutated=false",
    "live_dispatch_authorized=false — quality DR readiness pack only",
  ];

  const attach = composeHtmlNativeSourceAttach({
    session_id,
    parent_asset_id,
    requested_families: input.requested_families,
    sources: input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...attach.notes.map((n) => `[attach] ${n}`));

  const derive =
    input.derive_citations_from_sources === undefined
      ? true
      : input.derive_citations_from_sources;
  if (typeof derive !== "boolean") {
    throw new Error("derive_citations_from_sources must be boolean when set");
  }

  let citations: CitationRecord[];
  if (input.citations != null) {
    if (!Array.isArray(input.citations)) {
      throw new Error("citations must be an array when set");
    }
    citations = input.citations;
    notes.push(`citations=${citations.length} caller-supplied`);
  } else if (derive) {
    citations = deriveCitations(input.sources);
    notes.push(
      `citations=${citations.length} derived from HTML source refs (no invent titles)`,
    );
  } else {
    citations = [];
    notes.push("citations empty — neither supplied nor derived");
  }

  const citation_pack = buildDeepResearchSourceCitationPack({
    session_id,
    requested_families: input.requested_families as CitationFamily[],
    citations,
    filter_to_selected_families: true,
  });
  notes.push(...citation_pack.notes.map((n) => `[citation] ${n}`));

  const quality_gate = composeDeepResearchQualityBudgetGate({
    session_id,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    citation_pack_ready: citation_pack.pack_ready,
    operator_ack: input.operator_ack,
  });
  notes.push(...quality_gate.notes.map((n) => `[quality] ${n}`));

  const pack_ready =
    attach.attach_ready === true &&
    citation_pack.pack_ready === true &&
    quality_gate.gate_ready === true &&
    input.operator_ack === true;

  if (pack_ready) {
    notes.push(
      "pack_ready=true — source attach + citations + quality gate ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — attach, citation, quality, or operator_ack gate open",
    );
  }

  // Honesty reaffirmation
  if (
    attach.remote_fetched !== false ||
    attach.pdf_view_authorized !== false ||
    attach.store_mutated !== false ||
    citation_pack.remote_fetched !== false ||
    quality_gate.live_dispatch_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatch_authorized=false");

  return {
    session_id,
    parent_asset_id,
    attach,
    citation_pack,
    quality_gate,
    pack_ready,
    remote_fetched: false,
    pdf_view_authorized: false,
    store_mutated: false,
    live_dispatch_authorized: false,
    notes,
    authority: "source_publication_dr_attach_quality_compose_advisory",
  };
}

export function formatSourcePublicationDrAttachQualitySummary(
  c: SourcePublicationDrAttachQualityCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · attach=${c.attach.source_count} · ` +
    `citations=${c.citation_pack.citation_count} · ` +
    `html_ready=${c.attach.html_ready_count} · ` +
    `remote_fetched=false · pdf_view_authorized=false · ` +
    `live_dispatch_authorized=false`
  );
}
