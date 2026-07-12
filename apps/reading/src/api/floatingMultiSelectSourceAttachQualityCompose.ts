/**
 * Floating multi-select cohesive pack + source attach quality (pure).
 *
 * Operator vision: multi-select floating/sub-agent DR instances as one
 * cohesive unit, with arxiv/substack HTML sources under quality/budget gate
 * for the highest-quality deep research product.
 *
 * live_dispatched / pack_dispatched / merge_executed / analysis_written /
 * remote_fetched / pdf_view_authorized always false.
 */

import {
  composeFloatingMultiSelectCollectiveCohesive,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type FloatingMultiSelectMember,
  type MultiSelectPackMode,
} from "./floatingMultiSelectCollectiveCohesiveCompose";
import {
  composeSourcePublicationDrAttachQuality,
  type SourcePublicationDrAttachQualityCompose,
} from "./sourcePublicationDrAttachQualityCompose";
import type { HtmlNativeSourceRef } from "./htmlNativeSourceAttachCompose";
import type { CitationRecord } from "./deepResearchSourceCitationPack";
import type { PublicationFamily } from "./sourcePublicationRegistry";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";

export type { FloatingMultiSelectMember, MultiSelectPackMode };

export interface FloatingMultiSelectSourceAttachQualityInput {
  session_id: string;
  parent_asset_id: string;
  members: FloatingMultiSelectMember[];
  selected_instance_ids: string[];
  pack_mode: MultiSelectPackMode;
  cohesive_prompt: string;
  operator_ack: boolean;
  extra_context?: string[] | null;
  analysis_kind?: AnalysisMergeKind | null;
  extra_findings?: string[] | null;
  /** Source attach quality path. */
  requested_families: PublicationFamily[];
  sources: HtmlNativeSourceRef[];
  citations?: CitationRecord[] | null;
  derive_citations_from_sources?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  would_exceed: boolean | null;
  operator_override?: boolean;
  require_both?: boolean;
}

export interface FloatingMultiSelectSourceAttachQualityCompose {
  session_id: string;
  parent_asset_id: string;
  multi_select: FloatingMultiSelectCollectiveCohesiveCompose;
  source_quality: SourcePublicationDrAttachQualityCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  remote_fetched: false;
  pdf_view_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "floating_multi_select_source_attach_quality_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose multi-select cohesive DR pack + knowledge-dense source quality.
 * Never dispatches; never scrapes; never merges assets.
 */
export function composeFloatingMultiSelectSourceAttachQuality(
  input: FloatingMultiSelectSourceAttachQualityInput,
): FloatingMultiSelectSourceAttachQualityCompose {
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

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · pack_dispatched=false",
    "merge_executed=false · analysis_written=false",
    "remote_fetched=false — no live arxiv/substack scrape",
    "pdf_view_authorized=false — HTML-native sources only",
  ];

  const multi_select = composeFloatingMultiSelectCollectiveCohesive({
    session_id,
    parent_asset_id,
    members: input.members,
    selected_instance_ids: input.selected_instance_ids,
    pack_mode: input.pack_mode,
    cohesive_prompt: input.cohesive_prompt,
    operator_ack: input.operator_ack,
    extra_context: input.extra_context,
    analysis_kind: input.analysis_kind,
    extra_findings: input.extra_findings,
  });
  notes.push(...multi_select.notes.map((n) => `[multi_select] ${n}`));

  const source_quality = composeSourcePublicationDrAttachQuality({
    session_id,
    parent_asset_id,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    operator_ack: input.operator_ack,
  });
  notes.push(...source_quality.notes.map((n) => `[source_quality] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      multi_select.pack_ready === true &&
      source_quality.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (multi_select.pack_ready === true || source_quality.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — multi-select cohesive + source quality ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multi-select, source quality, or operator_ack gate open",
    );
  }

  if (
    multi_select.live_dispatched !== false ||
    multi_select.pack_dispatched !== false ||
    multi_select.merge_executed !== false ||
    multi_select.analysis_written !== false ||
    source_quality.remote_fetched !== false ||
    source_quality.pdf_view_authorized !== false ||
    source_quality.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    multi_select,
    source_quality,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    remote_fetched: false,
    pdf_view_authorized: false,
    store_mutated: false,
    notes,
    authority: "floating_multi_select_source_attach_quality_compose_advisory",
  };
}

export function formatFloatingMultiSelectSourceAttachQualitySummary(
  c: FloatingMultiSelectSourceAttachQualityCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multi_ready=${c.multi_select.pack_ready} · ` +
    `source_ready=${c.source_quality.pack_ready} · ` +
    `sources=${c.source_quality.attach.source_count} · ` +
    `live_dispatched=false · remote_fetched=false · analysis_written=false`
  );
}
