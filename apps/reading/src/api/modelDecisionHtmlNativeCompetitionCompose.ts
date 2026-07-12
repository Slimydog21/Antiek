/**
 * Model decision tree + usage/projection + HTML-native competition pack (pure).
 *
 * Operator vision: pick a model driver for competition-informed deep research
 * with budget bar + prompt projection, while the competition quality → write →
 * twin search pack remains HTML-native only — never live-route or PDF primary.
 *
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * pdf_view_authorized / pdf_primary always false.
 * live_dispatch_authorized / remote_fetched / remote_index_queried always false.
 * draft_written / analysis_written / merge_executed / twin_written always false.
 */

import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
  type SettingsDecisionTreeUsageBarInput,
} from "./settingsDecisionTreeUsageBarCompose";
import {
  composeHtmlNativeCompetitionWriteTwinSearch,
  type HtmlNativeCompetitionWriteTwinSearchCompose,
  type HtmlNativeCompetitionWriteTwinSearchInput,
} from "./htmlNativeCompetitionWriteTwinSearchCompose";

export interface ModelDecisionHtmlNativeCompetitionInput {
  decision: Omit<SettingsDecisionTreeUsageBarInput, "operator_ack">;
  competition_view: Omit<
    HtmlNativeCompetitionWriteTwinSearchInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require decision_ready, competition_view.pack_ready,
   * and would_exceed !== true (known over-budget blocks).
   */
  require_both?: boolean;
  /** When true (default), block pack if decision.would_exceed === true. */
  block_on_budget_exceed?: boolean;
}

export interface ModelDecisionHtmlNativeCompetitionCompose {
  session_id: string;
  asset_id: string;
  decision: SettingsDecisionTreeUsageBarCompose;
  competition_view: HtmlNativeCompetitionWriteTwinSearchCompose;
  pack_ready: boolean;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  remote_index_queried: false;
  twin_written: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "model_decision_html_native_competition_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose model decision/usage bar with HTML-native competition research pack.
 * Never live-routes, stores secrets, PDF-views, or writes assets.
 */
export function composeModelDecisionHtmlNativeCompetition(
  input: ModelDecisionHtmlNativeCompetitionInput,
): ModelDecisionHtmlNativeCompetitionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.decision || typeof input.decision !== "object") {
    throw new Error("decision must be an object");
  }
  if (!input.competition_view || typeof input.competition_view !== "object") {
    throw new Error("competition_view must be an object");
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

  const session_id = requireNonEmpty(
    input.competition_view.session_id,
    "competition_view.session_id",
  );
  const asset_id = requireNonEmpty(
    input.competition_view.asset_id,
    "competition_view.asset_id",
  );

  const notes: string[] = [
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "live_dispatch_authorized=false · remote_fetched=false · remote_index_queried=false",
    "draft_written=false · analysis_written=false · merge_executed=false · twin_written=false",
    "store_mutated=false · live_dispatched=false · backlog_mutated=false",
  ];

  const decision = composeSettingsDecisionTreeUsageBar({
    ...input.decision,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision.notes.map((n) => `[decision] ${n}`));

  const competition_view = composeHtmlNativeCompetitionWriteTwinSearch({
    ...input.competition_view,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition_view.notes.map((n) => `[competition_view] ${n}`));

  const budget_ok =
    !block_on_budget_exceed || decision.would_exceed !== true;
  if (!budget_ok) {
    notes.push(
      "budget_block=true — decision.would_exceed=true blocks pack_ready",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      decision.decision_ready === true &&
      competition_view.pack_ready === true &&
      budget_ok &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      budget_ok &&
      (decision.decision_ready === true ||
        competition_view.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — model decision + HTML-native competition pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — decision, competition_view, budget, or operator_ack gate open",
    );
  }

  if (
    decision.live_router_authorized !== false ||
    decision.secrets_stored !== false ||
    decision.live_meter_read !== false ||
    competition_view.pdf_view_authorized !== false ||
    competition_view.pdf_primary !== false ||
    competition_view.live_dispatch_authorized !== false ||
    competition_view.remote_fetched !== false ||
    competition_view.remote_index_queried !== false ||
    competition_view.draft_written !== false ||
    competition_view.twin_written !== false ||
    competition_view.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    asset_id,
    decision,
    competition_view,
    pack_ready,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    remote_index_queried: false,
    twin_written: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "model_decision_html_native_competition_compose_advisory",
  };
}

export function formatModelDecisionHtmlNativeCompetitionSummary(
  c: ModelDecisionHtmlNativeCompetitionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `decision_ready=${c.decision.decision_ready} · ` +
    `competition_ready=${c.competition_view.pack_ready} · ` +
    `would_exceed=${c.decision.would_exceed} · ` +
    `model=${c.decision.driver.decision.selected_model_id} · ` +
    `live_router_authorized=false · pdf_view_authorized=false · ` +
    `remote_index_queried=false · twin_written=false`
  );
}
