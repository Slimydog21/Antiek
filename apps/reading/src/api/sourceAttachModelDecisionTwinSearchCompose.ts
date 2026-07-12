/**
 * HTML-native source attach (arxiv/substack/…) over model decision + twin
 * search weekly HTML-native pack (pure).
 *
 * Operator vision: call knowledge-dense publications into deep research while
 * choosing the model driver with budget bar/projection and searching the twin
 * substrate — every source HTML-native, never remote-fetched in pure layer.
 *
 * remote_fetched always false.
 * pdf_view_authorized / pdf_primary always false.
 * live_router_authorized / secrets_stored always false.
 * production_router_verdict always REJECT.
 */

import {
  composeHtmlNativeSourceAttach,
  type HtmlNativeSourceAttachCompose,
  type HtmlNativeSourceAttachInput,
} from "./htmlNativeSourceAttachCompose";
import {
  composeModelDecisionTwinSearchWeeklyHtmlNative,
  type ModelDecisionTwinSearchWeeklyHtmlNativeCompose,
  type ModelDecisionTwinSearchWeeklyHtmlNativeInput,
} from "./modelDecisionTwinSearchWeeklyHtmlNativeCompose";

export interface SourceAttachModelDecisionTwinSearchInput {
  sources: Omit<HtmlNativeSourceAttachInput, "operator_ack">;
  decision_pack: Omit<
    ModelDecisionTwinSearchWeeklyHtmlNativeInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require attach_ready AND decision_pack.pack_ready,
   * session/parent alignment, and honesty gates.
   */
  require_both?: boolean;
}

export interface SourceAttachModelDecisionTwinSearchCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  week_id: string;
  sources: HtmlNativeSourceAttachCompose;
  decision_pack: ModelDecisionTwinSearchWeeklyHtmlNativeCompose;
  pack_ready: boolean;
  attach_ready: boolean;
  remote_fetched: false;
  store_mutated: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  suite_rewritten: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  notes: string[];
  authority: "source_attach_model_decision_twin_search_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * HTML-native arxiv/substack attach stacked on model decision + twin search
 * weekly pack. Never remote-fetches; never PDF-primary; ND REJECT.
 */
export function composeSourceAttachModelDecisionTwinSearch(
  input: SourceAttachModelDecisionTwinSearchInput,
): SourceAttachModelDecisionTwinSearchCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.sources || typeof input.sources !== "object") {
    throw new Error("sources must be an object");
  }
  if (!input.decision_pack || typeof input.decision_pack !== "object") {
    throw new Error("decision_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false — pure attach only (no live arxiv/substack)",
    "pdf_view_authorized=false · pdf_primary=false",
    "live_router_authorized=false · secrets_stored=false",
    "production_router_verdict=REJECT",
  ];

  const sources = composeHtmlNativeSourceAttach({
    ...input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...sources.notes.map((n) => `[sources] ${n}`));

  const decision_pack = composeModelDecisionTwinSearchWeeklyHtmlNative({
    ...input.decision_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision_pack.notes.map((n) => `[decision_pack] ${n}`));

  const session_id = requireNonEmpty(sources.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    sources.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(decision_pack.asset_id, "asset_id");
  const week_id = requireNonEmpty(decision_pack.week_id, "week_id");

  const session_aligned = decision_pack.session_id === session_id;
  const parent_aligned = decision_pack.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between sources and decision_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between sources and decision_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      sources.attach_ready === true &&
      decision_pack.pack_ready === true &&
      sources.remote_fetched === false &&
      sources.pdf_view_authorized === false &&
      sources.store_mutated === false &&
      decision_pack.production_router_verdict === "REJECT" &&
      decision_pack.pdf_primary === false &&
      decision_pack.live_router_authorized === false &&
      decision_pack.secrets_stored === false &&
      decision_pack.charge_executed === false &&
      decision_pack.suite_rewritten === false &&
      decision_pack.remote_index_queried === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      sources.remote_fetched === false &&
      sources.pdf_view_authorized === false &&
      decision_pack.production_router_verdict === "REJECT" &&
      decision_pack.pdf_primary === false &&
      (sources.attach_ready === true || decision_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — source attach + model decision twin search weekly ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — sources, decision_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    sources.remote_fetched !== false ||
    sources.pdf_view_authorized !== false ||
    sources.store_mutated !== false ||
    decision_pack.pdf_primary !== false ||
    decision_pack.live_router_authorized !== false ||
    decision_pack.secrets_stored !== false ||
    decision_pack.charge_executed !== false ||
    decision_pack.suite_rewritten !== false ||
    decision_pack.remote_index_queried !== false ||
    decision_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_fetched=false");
  notes.push("store_mutated=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");

  return {
    session_id,
    parent_asset_id,
    asset_id,
    week_id,
    sources,
    decision_pack,
    pack_ready,
    attach_ready: sources.attach_ready,
    remote_fetched: false,
    store_mutated: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    suite_rewritten: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    notes,
    authority: "source_attach_model_decision_twin_search_compose_advisory",
  };
}

export function formatSourceAttachModelDecisionTwinSearchSummary(
  c: SourceAttachModelDecisionTwinSearchCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `attach_ready=${c.attach_ready} · ` +
    `decision_ready=${c.decision_pack.pack_ready} · ` +
    `sources=${c.sources.source_count} · ` +
    `html_ready=${c.sources.html_ready_count} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_fetched=false · pdf_primary=false · suite_rewritten=false`
  );
}
