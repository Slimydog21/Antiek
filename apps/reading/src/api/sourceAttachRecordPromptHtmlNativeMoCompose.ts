/**
 * Source publication DR attach (arxiv/substack) + record→prompt HTML pack (pure).
 *
 * Operator vision: call arxiv, substack, and other knowledge-dense publications
 * into deep research as HTML-native refs with citation + quality gates, while
 * workstation records inform prompts with model budget projection over the
 * HTML-native recursive twin MO stack — never live-fetches or injects prompts.
 *
 * remote_fetched / live_dispatch_authorized always false.
 * record_persisted / prompts_injected always false.
 * pdf_view_authorized / pdf_primary always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeSourcePublicationDrAttachQuality,
  type SourcePublicationDrAttachQualityCompose,
  type SourcePublicationDrAttachQualityInput,
} from "./sourcePublicationDrAttachQualityCompose";
import {
  composeRecordPromptHtmlNativeRecursiveTwinMo,
  type RecordPromptHtmlNativeRecursiveTwinMoCompose,
  type RecordPromptHtmlNativeRecursiveTwinMoInput,
} from "./recordPromptHtmlNativeRecursiveTwinMoCompose";

export interface SourceAttachRecordPromptHtmlNativeMoInput {
  sources: Omit<SourcePublicationDrAttachQualityInput, "operator_ack">;
  record_html: Omit<
    RecordPromptHtmlNativeRecursiveTwinMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SourceAttachRecordPromptHtmlNativeMoCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  sources: SourcePublicationDrAttachQualityCompose;
  record_html: RecordPromptHtmlNativeRecursiveTwinMoCompose;
  pack_ready: boolean;
  remote_fetched: false;
  live_dispatch_authorized: false;
  record_persisted: false;
  prompts_injected: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  charge_executed: false;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  notes: string[];
  authority: "source_attach_record_prompt_html_native_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * arxiv/substack HTML attach + quality on record→prompt HTML-native pack.
 * Never remote-fetches; never injects prompts; never PDF primary.
 */
export function composeSourceAttachRecordPromptHtmlNativeMo(
  input: SourceAttachRecordPromptHtmlNativeMoInput,
): SourceAttachRecordPromptHtmlNativeMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.sources || typeof input.sources !== "object") {
    throw new Error("sources must be an object");
  }
  if (!input.record_html || typeof input.record_html !== "object") {
    throw new Error("record_html must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false · live_dispatch_authorized=false",
    "record_persisted=false · prompts_injected=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const sources = composeSourcePublicationDrAttachQuality({
    ...input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...sources.notes.map((n) => `[sources] ${n}`));

  const record_html = composeRecordPromptHtmlNativeRecursiveTwinMo({
    ...input.record_html,
    operator_ack: input.operator_ack,
  });
  notes.push(...record_html.notes.map((n) => `[record_html] ${n}`));

  const session_id = requireNonEmpty(sources.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    sources.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(record_html.week_id, "week_id");

  const aligned =
    record_html.session_id === session_id &&
    record_html.parent_asset_id === parent_asset_id;
  if (!aligned) {
    notes.push(
      "session/parent mismatch between sources and record_html — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      aligned &&
      sources.pack_ready === true &&
      record_html.pack_ready === true &&
      record_html.production_router_verdict === "REJECT" &&
      sources.remote_fetched === false &&
      sources.pdf_view_authorized === false &&
      record_html.prompts_injected === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      record_html.production_router_verdict === "REJECT" &&
      sources.remote_fetched === false &&
      (sources.pack_ready === true || record_html.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — arxiv/substack attach + record→prompt HTML pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — sources, record_html, alignment, or operator_ack gate open",
    );
  }

  if (
    sources.remote_fetched !== false ||
    sources.live_dispatch_authorized !== false ||
    sources.pdf_view_authorized !== false ||
    sources.store_mutated !== false ||
    record_html.record_persisted !== false ||
    record_html.prompts_injected !== false ||
    record_html.pdf_primary !== false ||
    record_html.twin_written !== false ||
    record_html.production_router_verdict !== "REJECT" ||
    record_html.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_fetched=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("purchase_executed=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    sources,
    record_html,
    pack_ready,
    remote_fetched: false,
    live_dispatch_authorized: false,
    record_persisted: false,
    prompts_injected: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    charge_executed: false,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    notes,
    authority: "source_attach_record_prompt_html_native_mo_compose_advisory",
  };
}

export function formatSourceAttachRecordPromptHtmlNativeMoSummary(
  c: SourceAttachRecordPromptHtmlNativeMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `sources_ready=${c.sources.pack_ready} · ` +
    `citations=${c.sources.citation_pack.citation_count} · ` +
    `record_html_ready=${c.record_html.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_fetched=false · prompts_injected=false · pdf_primary=false`
  );
}
