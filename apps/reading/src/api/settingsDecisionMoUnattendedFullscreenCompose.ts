/**
 * Settings decision-tree usage bar over Midnight Oil unattended + fullscreen
 * draft collective pack (pure).
 *
 * Operator vision: model decision tree tab with usage bar against budget and
 * prompt projection — available while MO unattended + fullscreen draft
 * collective pack is ready. Never live-routes or stores secrets.
 *
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * live_execution_authorized / purchase_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
  type SettingsDecisionTreeUsageBarInput,
} from "./settingsDecisionTreeUsageBarCompose";
import {
  composeMoUnattendedFullscreenDraftCollective,
  type MoUnattendedFullscreenDraftCollectiveCompose,
  type MoUnattendedFullscreenDraftCollectiveInput,
} from "./moUnattendedFullscreenDraftCollectiveCompose";

export interface SettingsDecisionMoUnattendedFullscreenInput {
  decision: Omit<SettingsDecisionTreeUsageBarInput, "operator_ack">;
  mo_pack: Omit<MoUnattendedFullscreenDraftCollectiveInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require decision_ready AND mo_pack.pack_ready.
   * would_exceed=true blocks pack_ready under require_both.
   */
  require_both?: boolean;
}

export interface SettingsDecisionMoUnattendedFullscreenCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  decision: SettingsDecisionTreeUsageBarCompose;
  mo_pack: MoUnattendedFullscreenDraftCollectiveCompose;
  pack_ready: boolean;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  live_execution_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  remote_index_queried: false;
  inventory_mutated: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "settings_decision_mo_unattended_fullscreen_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Settings decision-tree + usage bar stacked on MO unattended fullscreen pack.
 * Never live-routes; never charges; ND REJECT.
 */
export function composeSettingsDecisionMoUnattendedFullscreen(
  input: SettingsDecisionMoUnattendedFullscreenInput,
): SettingsDecisionMoUnattendedFullscreenCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.decision || typeof input.decision !== "object") {
    throw new Error("decision must be an object");
  }
  if (!input.mo_pack || typeof input.mo_pack !== "object") {
    throw new Error("mo_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "live_execution_authorized=false · purchase_executed=false",
    "production_router_verdict=REJECT",
  ];

  const decision = composeSettingsDecisionTreeUsageBar({
    ...input.decision,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision.notes.map((n) => `[decision] ${n}`));

  const mo_pack = composeMoUnattendedFullscreenDraftCollective({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const session_id = requireNonEmpty(mo_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    mo_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(mo_pack.title, "title");
  const account_id = requireNonEmpty(mo_pack.account_id, "account_id");
  const week_id = requireNonEmpty(mo_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(mo_pack.asset_id, "asset_id");

  // Budget honesty: would_exceed=true blocks pack under require_both.
  const budget_ok = decision.would_exceed !== true;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      budget_ok &&
      decision.decision_ready === true &&
      mo_pack.pack_ready === true &&
      decision.live_router_authorized === false &&
      decision.secrets_stored === false &&
      decision.live_meter_read === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.live_dispatched === false &&
      mo_pack.merge_executed === false &&
      mo_pack.draft_written === false &&
      mo_pack.purchase_executed === false &&
      mo_pack.live_router_authorized === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      decision.live_router_authorized === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.purchase_executed === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      (decision.decision_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — settings decision + MO unattended fullscreen ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — decision, mo_pack, would_exceed, or operator_ack gate open",
    );
  }

  if (
    decision.live_router_authorized !== false ||
    decision.secrets_stored !== false ||
    decision.live_meter_read !== false ||
    mo_pack.live_execution_authorized !== false ||
    mo_pack.live_dispatched !== false ||
    mo_pack.merge_executed !== false ||
    mo_pack.draft_written !== false ||
    mo_pack.purchase_executed !== false ||
    mo_pack.live_router_authorized !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("remote_index_queried=false");
  notes.push("inventory_mutated=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    title,
    account_id,
    week_id,
    asset_id,
    decision,
    mo_pack,
    pack_ready,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    live_execution_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    remote_index_queried: false,
    inventory_mutated: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "settings_decision_mo_unattended_fullscreen_compose_advisory",
  };
}

export function formatSettingsDecisionMoUnattendedFullscreenSummary(
  c: SettingsDecisionMoUnattendedFullscreenCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `decision_ready=${c.decision.decision_ready} · ` +
    `usage_percent=${c.decision.usage_percent ?? "null"} · ` +
    `would_exceed=${c.decision.would_exceed ?? "null"} · ` +
    `mo_ready=${c.mo_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · live_execution_authorized=false`
  );
}
