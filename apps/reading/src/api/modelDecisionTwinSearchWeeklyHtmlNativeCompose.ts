/**
 * Model decision-tree + usage bar + prompt projection over twin search +
 * Antiek-bench weekly HTML-native pack (pure).
 *
 * Operator vision: choose the AI model driver for any prompt with usage bar
 * against budget and projection of how the proposed prompt affects the limit,
 * while twin intelligent search + weekly bench + HTML-native honesty remain
 * pure — never live-route, store secrets, or PDF-primary.
 *
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * remote_index_queried / suite_rewritten / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
  type SettingsDecisionTreeUsageBarInput,
} from "./settingsDecisionTreeUsageBarCompose";
import {
  composeTwinSearchAntiekBenchWeeklyHtmlNative,
  type TwinSearchAntiekBenchWeeklyHtmlNativeCompose,
  type TwinSearchAntiekBenchWeeklyHtmlNativeInput,
} from "./twinSearchAntiekBenchWeeklyHtmlNativeCompose";

export interface ModelDecisionTwinSearchWeeklyHtmlNativeInput {
  decision: Omit<SettingsDecisionTreeUsageBarInput, "operator_ack">;
  twin_search_pack: Omit<
    TwinSearchAntiekBenchWeeklyHtmlNativeInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require decision_ready AND twin_search_pack.pack_ready.
   */
  require_both?: boolean;
  /** When true (default), block pack if decision.would_exceed === true. */
  block_on_budget_exceed?: boolean;
}

export interface ModelDecisionTwinSearchWeeklyHtmlNativeCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  decision: SettingsDecisionTreeUsageBarCompose;
  twin_search_pack: TwinSearchAntiekBenchWeeklyHtmlNativeCompose;
  pack_ready: boolean;
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
  authority: "model_decision_twin_search_weekly_html_native_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Model decision/usage/projection stacked on twin search weekly HTML-native.
 * Never live-routes; never mutates bench; never PDF-primary; ND REJECT.
 */
export function composeModelDecisionTwinSearchWeeklyHtmlNative(
  input: ModelDecisionTwinSearchWeeklyHtmlNativeInput,
): ModelDecisionTwinSearchWeeklyHtmlNativeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.decision || typeof input.decision !== "object") {
    throw new Error("decision must be an object");
  }
  if (!input.twin_search_pack || typeof input.twin_search_pack !== "object") {
    throw new Error("twin_search_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }
  const block_on_budget_exceed =
    input.block_on_budget_exceed === undefined
      ? true
      : input.block_on_budget_exceed;
  if (typeof block_on_budget_exceed !== "boolean") {
    throw new Error("block_on_budget_exceed must be boolean when set");
  }

  const notes: string[] = [
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "remote_index_queried=false · suite_rewritten=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const decision = composeSettingsDecisionTreeUsageBar({
    ...input.decision,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision.notes.map((n) => `[decision] ${n}`));

  const twin_search_pack = composeTwinSearchAntiekBenchWeeklyHtmlNative({
    ...input.twin_search_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin_search_pack.notes.map((n) => `[twin_search_pack] ${n}`));

  const week_id = requireNonEmpty(twin_search_pack.week_id, "week_id");
  const session_id = requireNonEmpty(twin_search_pack.session_id, "session_id");
  const asset_id = requireNonEmpty(twin_search_pack.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    twin_search_pack.parent_asset_id,
    "parent_asset_id",
  );

  const budget_ok =
    !block_on_budget_exceed || decision.would_exceed !== true;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      decision.decision_ready === true &&
      twin_search_pack.pack_ready === true &&
      budget_ok &&
      decision.live_router_authorized === false &&
      decision.secrets_stored === false &&
      twin_search_pack.remote_index_queried === false &&
      twin_search_pack.suite_rewritten === false &&
      twin_search_pack.production_router_verdict === "REJECT" &&
      twin_search_pack.pdf_primary === false &&
      twin_search_pack.twin_written === false &&
      twin_search_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      budget_ok &&
      decision.live_router_authorized === false &&
      twin_search_pack.production_router_verdict === "REJECT" &&
      twin_search_pack.pdf_primary === false &&
      (decision.decision_ready === true || twin_search_pack.pack_ready === true);
  }

  if (!budget_ok) {
    notes.push(
      "would_exceed=true — pack_ready blocked by budget projection gate",
    );
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — model decision + twin search weekly HTML-native ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — decision, twin_search_pack, budget, or operator_ack gate open",
    );
  }

  if (
    decision.live_router_authorized !== false ||
    decision.secrets_stored !== false ||
    decision.live_meter_read !== false ||
    twin_search_pack.remote_index_queried !== false ||
    twin_search_pack.suite_rewritten !== false ||
    twin_search_pack.pdf_primary !== false ||
    twin_search_pack.twin_written !== false ||
    twin_search_pack.charge_executed !== false ||
    twin_search_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

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
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    decision,
    twin_search_pack,
    pack_ready,
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
    authority:
      "model_decision_twin_search_weekly_html_native_compose_advisory",
  };
}

export function formatModelDecisionTwinSearchWeeklyHtmlNativeSummary(
  c: ModelDecisionTwinSearchWeeklyHtmlNativeCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `decision_ready=${c.decision.decision_ready} · ` +
    `search_ready=${c.twin_search_pack.pack_ready} · ` +
    `would_exceed=${c.decision.would_exceed} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · suite_rewritten=false · pdf_primary=false`
  );
}
