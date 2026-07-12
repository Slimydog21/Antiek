/**
 * Twin intelligent search residual over model decision budget + HTML-native
 * settings marketplace free competition DR ND pack (pure).
 *
 * Operator vision: intelligent search over the twin substrate of the infinite
 * information platform, stacked on model decision-tree usage bar + budget
 * projection + HTML-native view + free-first marketplace + BYOK settings +
 * competition DR + NotDiamond REJECT honesty — without remote index, twin
 * writes, purchases, live routing, or PDF-primary views.
 *
 * remote_index_queried always false.
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * pdf_primary / purchase_executed / hosted / twin_written always false.
 * production_router_verdict always REJECT.
 * require_both (default) needs ≥1 search hit AND model_decision_pack.pack_ready.
 */

import {
  searchTwinSubstrate,
  type TwinSearchRecord,
  type TwinSearchResult,
} from "./recursiveTwinIntelligentSearch";
import {
  composeModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNd,
  type ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
  type ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput,
} from "./modelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose";

export interface TwinSearchModelDecisionHtmlNativeSettingsMarketplaceInput {
  search_query: string;
  twin_records: TwinSearchRecord[];
  search_limit?: number;
  model_decision_pack: Omit<
    ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require ≥1 search hit AND model_decision_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  search: TwinSearchResult;
  model_decision_pack: ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose;
  hit_count: number;
  pack_ready: boolean;
  remote_index_queried: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  store_mutated: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  backlog_mutated: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_meter_read: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  charge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "twin_search_model_decision_html_native_settings_marketplace_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Twin substrate search stacked on model decision HTML-native settings marketplace pack.
 * Never remote-indexes; never PDF-primary; never writes twins; ND REJECT.
 */
export function composeTwinSearchModelDecisionHtmlNativeSettingsMarketplace(
  input: TwinSearchModelDecisionHtmlNativeSettingsMarketplaceInput,
): TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.model_decision_pack || typeof input.model_decision_pack !== "object") {
    throw new Error("model_decision_pack must be an object");
  }
  if (!Array.isArray(input.twin_records)) {
    throw new Error("twin_records must be an array");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_index_queried=false — pure substrate scan only",
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "pdf_primary=false · twin_written=false · purchase_executed=false",
    "production_router_verdict=REJECT",
  ];

  const search = searchTwinSubstrate({
    query: input.search_query,
    records: input.twin_records,
    limit: input.search_limit,
  });
  notes.push(...search.notes.map((n) => `[search] ${n}`));

  const model_decision_pack =
    composeModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNd({
      ...input.model_decision_pack,
      operator_ack: input.operator_ack,
    });
  notes.push(
    ...model_decision_pack.notes.map((n) => `[model_decision_pack] ${n}`),
  );

  const session_id = requireNonEmpty(
    model_decision_pack.session_id,
    "session_id",
  );
  const parent_asset_id = requireNonEmpty(
    model_decision_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(model_decision_pack.asset_id, "asset_id");
  const title = requireNonEmpty(model_decision_pack.title, "title");
  const account_id = requireNonEmpty(
    model_decision_pack.account_id,
    "account_id",
  );
  const week_id = requireNonEmpty(model_decision_pack.week_id, "week_id");
  const hit_count = search.hits.length;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      hit_count >= 1 &&
      model_decision_pack.pack_ready === true &&
      search.remote_index_queried === false &&
      model_decision_pack.live_router_authorized === false &&
      model_decision_pack.secrets_stored === false &&
      model_decision_pack.live_meter_read === false &&
      model_decision_pack.pdf_view_authorized === false &&
      model_decision_pack.pdf_primary === false &&
      model_decision_pack.twin_written === false &&
      model_decision_pack.purchase_executed === false &&
      model_decision_pack.hosted === false &&
      model_decision_pack.inventory_mutated === false &&
      model_decision_pack.remote_index_queried === false &&
      model_decision_pack.suite_rewritten === false &&
      model_decision_pack.charge_executed === false &&
      model_decision_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      search.remote_index_queried === false &&
      model_decision_pack.live_router_authorized === false &&
      model_decision_pack.pdf_primary === false &&
      model_decision_pack.twin_written === false &&
      model_decision_pack.purchase_executed === false &&
      model_decision_pack.production_router_verdict === "REJECT" &&
      (hit_count >= 1 || model_decision_pack.pack_ready === true);
  }

  if (hit_count < 1 && require_both) {
    notes.push(
      "zero search hits — pack_ready blocked under require_both (≥1 hit gate)",
    );
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin search + model decision HTML-native settings marketplace ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — search hits, model_decision_pack, or operator_ack gate open",
    );
  }

  if (
    search.remote_index_queried !== false ||
    model_decision_pack.live_router_authorized !== false ||
    model_decision_pack.secrets_stored !== false ||
    model_decision_pack.live_meter_read !== false ||
    model_decision_pack.pdf_view_authorized !== false ||
    model_decision_pack.pdf_primary !== false ||
    model_decision_pack.twin_written !== false ||
    model_decision_pack.purchase_executed !== false ||
    model_decision_pack.hosted !== false ||
    model_decision_pack.inventory_mutated !== false ||
    model_decision_pack.remote_index_queried !== false ||
    model_decision_pack.suite_rewritten !== false ||
    model_decision_pack.charge_executed !== false ||
    model_decision_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("remote_index_queried=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("store_mutated=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_meter_read=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    week_id,
    search,
    model_decision_pack,
    hit_count,
    pack_ready,
    remote_index_queried: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    store_mutated: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    backlog_mutated: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_meter_read: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    charge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "twin_search_model_decision_html_native_settings_marketplace_compose_advisory",
  };
}

export function formatTwinSearchModelDecisionHtmlNativeSettingsMarketplaceSummary(
  c: TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `hits=${c.hit_count} · ` +
    `decision_ready=${c.model_decision_pack.decision.decision_ready} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_index_queried=false · pdf_primary=false · twin_written=false`
  );
}
