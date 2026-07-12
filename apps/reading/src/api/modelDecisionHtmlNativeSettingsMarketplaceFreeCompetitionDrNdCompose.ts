/**
 * Model decision-tree + usage bar + prompt projection residual over HTML-native
 * settings add-model marketplace free competition DR ND pack (pure).
 *
 * Operator vision: choose the AI model driver for any prompt with usage bar
 * against budget and projection of how the proposed prompt affects the limit,
 * while HTML-native view + BYOK settings inventory + free-first marketplace +
 * competition DR quality + NotDiamond REJECT honesty remain pure — never
 * live-route, store secrets, purchase/host, or PDF-primary.
 *
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * pdf_primary / purchase_executed / hosted / inventory_mutated always false.
 * production_router_verdict always REJECT.
 * would_exceed=true blocks pack_ready under block_on_budget_exceed (default).
 */

import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
  type SettingsDecisionTreeUsageBarInput,
} from "./settingsDecisionTreeUsageBarCompose";
import {
  composeHtmlNativeSettingsMarketplaceFreeCompetitionDrNd,
  type HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
  type HtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput,
} from "./htmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose";

export interface ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput {
  decision: Omit<SettingsDecisionTreeUsageBarInput, "operator_ack">;
  html_native_pack: Omit<
    HtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require decision_ready AND html_native_pack.pack_ready.
   */
  require_both?: boolean;
  /** When true (default), block pack if decision.would_exceed === true. */
  block_on_budget_exceed?: boolean;
}

export interface ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  focus_task: string | null;
  decision: SettingsDecisionTreeUsageBarCompose;
  html_native_pack: HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose;
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
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Model decision/usage/projection stacked on HTML-native settings marketplace free competition DR ND.
 * Never live-routes; never mutates inventory; never PDF-primary; ND REJECT.
 */
export function composeModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNd(
  input: ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput,
): ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.decision || typeof input.decision !== "object") {
    throw new Error("decision must be an object");
  }
  if (!input.html_native_pack || typeof input.html_native_pack !== "object") {
    throw new Error("html_native_pack must be an object");
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
    "pdf_primary=false · purchase_executed=false · inventory_mutated=false",
    "production_router_verdict=REJECT",
  ];

  const decision = composeSettingsDecisionTreeUsageBar({
    ...input.decision,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision.notes.map((n) => `[decision] ${n}`));

  const html_native_pack = composeHtmlNativeSettingsMarketplaceFreeCompetitionDrNd({
    ...input.html_native_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_native_pack.notes.map((n) => `[html_native_pack] ${n}`));

  const week_id = requireNonEmpty(html_native_pack.week_id, "week_id");
  const session_id = requireNonEmpty(html_native_pack.session_id, "session_id");
  const asset_id = requireNonEmpty(html_native_pack.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    html_native_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(html_native_pack.title, "title");
  const account_id = requireNonEmpty(html_native_pack.account_id, "account_id");

  let focus_task: string | null = null;
  if (
    typeof input.decision.focus_task === "string" &&
    input.decision.focus_task.trim()
  ) {
    focus_task = input.decision.focus_task.trim();
  }

  const budget_ok =
    !block_on_budget_exceed || decision.would_exceed !== true;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      decision.decision_ready === true &&
      html_native_pack.pack_ready === true &&
      budget_ok &&
      decision.live_router_authorized === false &&
      decision.secrets_stored === false &&
      decision.live_meter_read === false &&
      html_native_pack.production_router_verdict === "REJECT" &&
      html_native_pack.pdf_primary === false &&
      html_native_pack.pdf_view_authorized === false &&
      html_native_pack.secrets_stored === false &&
      html_native_pack.inventory_mutated === false &&
      html_native_pack.purchase_executed === false &&
      html_native_pack.hosted === false &&
      html_native_pack.live_dispatch_authorized === false &&
      html_native_pack.remote_fetched === false &&
      html_native_pack.live_router_authorized === false &&
      html_native_pack.twin_written === false &&
      html_native_pack.merge_executed === false &&
      html_native_pack.draft_written === false &&
      html_native_pack.remote_index_queried === false &&
      html_native_pack.suite_rewritten === false &&
      html_native_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      budget_ok &&
      decision.live_router_authorized === false &&
      html_native_pack.production_router_verdict === "REJECT" &&
      html_native_pack.pdf_primary === false &&
      html_native_pack.purchase_executed === false &&
      (decision.decision_ready === true || html_native_pack.pack_ready === true);
  }

  if (!budget_ok) {
    notes.push(
      "would_exceed=true — pack_ready blocked by budget projection gate",
    );
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — model decision + HTML-native settings marketplace free competition DR ND ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — decision, html_native_pack, budget, or operator_ack gate open",
    );
  }

  if (
    decision.live_router_authorized !== false ||
    decision.secrets_stored !== false ||
    decision.live_meter_read !== false ||
    html_native_pack.pdf_primary !== false ||
    html_native_pack.pdf_view_authorized !== false ||
    html_native_pack.secrets_stored !== false ||
    html_native_pack.inventory_mutated !== false ||
    html_native_pack.purchase_executed !== false ||
    html_native_pack.hosted !== false ||
    html_native_pack.live_dispatch_authorized !== false ||
    html_native_pack.remote_fetched !== false ||
    html_native_pack.live_router_authorized !== false ||
    html_native_pack.twin_written !== false ||
    html_native_pack.merge_executed !== false ||
    html_native_pack.draft_written !== false ||
    html_native_pack.remote_index_queried !== false ||
    html_native_pack.suite_rewritten !== false ||
    html_native_pack.charge_executed !== false ||
    html_native_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
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
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    focus_task,
    decision,
    html_native_pack,
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
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_advisory",
  };
}

export function formatModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdSummary(
  c: ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
): string {
  const budget =
    c.decision.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${c.decision.would_exceed}`;
  const task = c.focus_task ?? "null";
  return (
    `pack_ready=${c.pack_ready} · ` +
    `decision_ready=${c.decision.decision_ready} · ` +
    `model=${c.decision.driver.decision.selected_model_id} · ` +
    `${budget} · ` +
    `html_ready=${c.html_native_pack.pack_ready} · ` +
    `week=${c.week_id} · task=${task} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · secrets_stored=false · pdf_primary=false`
  );
}
