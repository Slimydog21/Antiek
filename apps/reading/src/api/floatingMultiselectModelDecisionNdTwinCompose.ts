/**
 * Floating multi-select collective cohesive residual over model decision
 * budget + twin search HTML-native marketplace free settings ND twin pack (pure).
 *
 * Operator vision: multi-select floating/sub-agent deep research instances as
 * one cohesive unit while model driver decision tree + usage/projection bar
 * rides twin intelligent search + HTML-native free marketplace + settings +
 * NotDiamond REJECT + twin presentation — without live dispatch, pack
 * execution, secret store, or budget overage.
 *
 * live_dispatched / pack_dispatched / merge_executed always false.
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * remote_index_queried / suite_rewritten / pdf_primary always false.
 * production_router_verdict always REJECT.
 * would_exceed=true on nested decision blocks pack_ready under require_both.
 */

import {
  composeFloatingMultiSelectCollectiveCohesive,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type FloatingMultiSelectCollectiveCohesiveInput,
} from "./floatingMultiSelectCollectiveCohesiveCompose";
import {
  composeModelDecisionTwinSearchHtmlNativeNdTwin,
  type ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsNdTwinCompose,
  type ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsNdTwinInput,
} from "./modelDecisionTwinSearchHtmlNativeNdTwinCompose";

export interface FloatingMultiselectModelDecisionNdTwinInput {
  multiselect: Omit<
    FloatingMultiSelectCollectiveCohesiveInput,
    "operator_ack"
  >;
  decision_pack: Omit<
    ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsNdTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require multiselect.pack_ready AND decision_pack.pack_ready
   * and session/parent alignment.
   */
  require_both?: boolean;
}

export interface FloatingMultiselectModelDecisionNdTwinCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  multiselect: FloatingMultiSelectCollectiveCohesiveCompose;
  decision_pack: ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsNdTwinCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "floating_multiselect_model_decision_nd_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Floating multi-select cohesive pack stacked on model decision budget + twin
 * search HTML-native ND twin. Never live-dispatches or over-budgets.
 */
export function composeFloatingMultiselectModelDecisionNdTwin(
  input: FloatingMultiselectModelDecisionNdTwinInput,
): FloatingMultiselectModelDecisionNdTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.multiselect || typeof input.multiselect !== "object") {
    throw new Error("multiselect must be an object");
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
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "remote_index_queried=false · suite_rewritten=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const multiselect = composeFloatingMultiSelectCollectiveCohesive({
    ...input.multiselect,
    operator_ack: input.operator_ack,
  });
  notes.push(...multiselect.notes.map((n) => `[multiselect] ${n}`));

  const decision_pack = composeModelDecisionTwinSearchHtmlNativeNdTwin({
    ...input.decision_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision_pack.notes.map((n) => `[decision_pack] ${n}`));

  const session_id = requireNonEmpty(multiselect.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    multiselect.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(decision_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(decision_pack.asset_id, "asset_id");
  const title = requireNonEmpty(decision_pack.title, "title");
  const account_id = requireNonEmpty(decision_pack.account_id, "account_id");

  const session_aligned = decision_pack.session_id === session_id;
  const parent_aligned =
    decision_pack.parent_asset_id === parent_asset_id ||
    decision_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between multiselect and decision_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between multiselect and decision_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      multiselect.pack_ready === true &&
      decision_pack.pack_ready === true &&
      decision_pack.production_router_verdict === "REJECT" &&
      decision_pack.decision.would_exceed !== true &&
      decision_pack.live_router_authorized === false &&
      decision_pack.secrets_stored === false &&
      decision_pack.live_meter_read === false &&
      decision_pack.remote_index_queried === false &&
      decision_pack.pdf_primary === false &&
      multiselect.live_dispatched === false &&
      multiselect.pack_dispatched === false &&
      multiselect.merge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      decision_pack.production_router_verdict === "REJECT" &&
      decision_pack.pdf_primary === false &&
      (multiselect.pack_ready === true || decision_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — floating multi-select + model decision ND twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multiselect, decision_pack, alignment, budget, or operator_ack gate open",
    );
  }

  if (
    multiselect.live_dispatched !== false ||
    multiselect.pack_dispatched !== false ||
    multiselect.merge_executed !== false ||
    decision_pack.live_router_authorized !== false ||
    decision_pack.secrets_stored !== false ||
    decision_pack.live_meter_read !== false ||
    decision_pack.remote_index_queried !== false ||
    decision_pack.pdf_primary !== false ||
    decision_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    multiselect,
    decision_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "floating_multiselect_model_decision_nd_twin_compose_advisory",
  };
}

export function formatFloatingMultiselectModelDecisionNdTwinSummary(
  c: FloatingMultiselectModelDecisionNdTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multiselect_ready=${c.multiselect.pack_ready} · ` +
    `decision_ready=${c.decision_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · pack_dispatched=false · live_router_authorized=false`
  );
}
