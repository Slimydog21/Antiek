/**
 * Midnight Oil unattended package (time+goals+price ceiling) over source
 * attach + model decision twin search pack (pure).
 *
 * Operator vision: set work window and goals; approve recommended price
 * ceiling; package is ready for unattended deep research beside HTML-native
 * arxiv/substack attach + model driver budget — never live-executes or charges.
 *
 * live_execution_authorized always false.
 * charge_executed always false.
 * remote_fetched / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMidnightOilPriceCeilingApproval,
  type MidnightOilPriceCeilingApprovalCompose,
  type MidnightOilPriceCeilingApprovalInput,
} from "./midnightOilPriceCeilingApprovalCompose";
import {
  composeSourceAttachModelDecisionTwinSearch,
  type SourceAttachModelDecisionTwinSearchCompose,
  type SourceAttachModelDecisionTwinSearchInput,
} from "./sourceAttachModelDecisionTwinSearchCompose";

export interface MoUnattendedSourceAttachModelDecisionInput {
  mo: Omit<MidnightOilPriceCeilingApprovalInput, "operator_ack">;
  research_pack: Omit<
    SourceAttachModelDecisionTwinSearchInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require mo.pack_ready AND research_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface MoUnattendedSourceAttachModelDecisionCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  week_id: string;
  operator_id: string;
  mo: MidnightOilPriceCeilingApprovalCompose;
  research_pack: SourceAttachModelDecisionTwinSearchCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  charge_executed: false;
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
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  notes: string[];
  authority: "mo_unattended_source_attach_model_decision_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * MO unattended price-ceiling package stacked on source attach + model
 * decision twin search. Never live-executes; never charges.
 */
export function composeMoUnattendedSourceAttachModelDecision(
  input: MoUnattendedSourceAttachModelDecisionInput,
): MoUnattendedSourceAttachModelDecisionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.research_pack || typeof input.research_pack !== "object") {
    throw new Error("research_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false · charge_executed=false",
    "remote_fetched=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const mo = composeMidnightOilPriceCeilingApproval({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const research_pack = composeSourceAttachModelDecisionTwinSearch({
    ...input.research_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...research_pack.notes.map((n) => `[research_pack] ${n}`));

  const session_id = requireNonEmpty(research_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    research_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(research_pack.asset_id, "asset_id");
  const week_id = requireNonEmpty(research_pack.week_id, "week_id");
  const operator_id = requireNonEmpty(mo.operator_id, "operator_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.pack_ready === true &&
      research_pack.pack_ready === true &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      research_pack.remote_fetched === false &&
      research_pack.pdf_primary === false &&
      research_pack.live_router_authorized === false &&
      research_pack.secrets_stored === false &&
      research_pack.charge_executed === false &&
      research_pack.suite_rewritten === false &&
      research_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      research_pack.production_router_verdict === "REJECT" &&
      research_pack.pdf_primary === false &&
      (mo.pack_ready === true || research_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO unattended + source attach model decision ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, research_pack, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    mo.charge_executed !== false ||
    research_pack.remote_fetched !== false ||
    research_pack.pdf_primary !== false ||
    research_pack.live_router_authorized !== false ||
    research_pack.secrets_stored !== false ||
    research_pack.charge_executed !== false ||
    research_pack.suite_rewritten !== false ||
    research_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
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
    operator_id,
    mo,
    research_pack,
    pack_ready,
    live_execution_authorized: false,
    charge_executed: false,
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
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    notes,
    authority: "mo_unattended_source_attach_model_decision_compose_advisory",
  };
}

export function formatMoUnattendedSourceAttachModelDecisionSummary(
  c: MoUnattendedSourceAttachModelDecisionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.pack_ready} · ` +
    `research_ready=${c.research_pack.pack_ready} · ` +
    `stage=${c.mo.stage} · ` +
    `ceiling_approved=${c.mo.ceiling_approved} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_execution_authorized=false · charge_executed=false · remote_fetched=false`
  );
}
