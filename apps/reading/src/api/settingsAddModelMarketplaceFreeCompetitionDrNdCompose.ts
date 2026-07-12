/**
 * Settings add-model inventory residual over marketplace free-before-buy +
 * competition DR + NotDiamond shadow REJECT + source-attach + weekly learn +
 * recursive twin presentation write collective pack (pure).
 *
 * Operator vision: add models in settings (BYOK ids only) with budget bar /
 * projection while free-first marketplace + competition DR + ND shadow honesty
 * remain pure — never store secrets, never mutate inventory, never live-route.
 *
 * secrets_stored / inventory_mutated always false.
 * purchase_executed / hosted always false.
 * live_router_authorized always false; production_router_verdict always REJECT.
 */

import {
  composeSettingsAddModelInventory,
  type SettingsAddModelInventoryCompose,
  type SettingsAddModelInventoryInput,
} from "./settingsAddModelInventoryCompose";
import {
  composeMarketplaceFreeCompetitionDrNdShadowSourceAttach,
  type MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose,
  type MarketplaceFreeCompetitionDrNdShadowSourceAttachInput,
} from "./marketplaceFreeCompetitionDrNdShadowSourceAttachCompose";

export interface SettingsAddModelMarketplaceFreeCompetitionDrNdInput {
  settings: Omit<SettingsAddModelInventoryInput, "operator_ack">;
  market_pack: Omit<
    MarketplaceFreeCompetitionDrNdShadowSourceAttachInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SettingsAddModelMarketplaceFreeCompetitionDrNdCompose {
  title: string;
  account_id: string;
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  settings: SettingsAddModelInventoryCompose;
  market_pack: MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose;
  pack_ready: boolean;
  secrets_stored: false;
  inventory_mutated: false;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  live_meter_read: false;
  remote_index_queried: false;
  charge_executed: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "settings_add_model_marketplace_free_competition_dr_nd_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Settings add-model inventory overlay on marketplace free competition DR ND pack.
 * Never stores secrets; never mutates inventory; never purchases; ND REJECT.
 */
export function composeSettingsAddModelMarketplaceFreeCompetitionDrNd(
  input: SettingsAddModelMarketplaceFreeCompetitionDrNdInput,
): SettingsAddModelMarketplaceFreeCompetitionDrNdCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.settings || typeof input.settings !== "object") {
    throw new Error("settings must be an object");
  }
  if (!input.market_pack || typeof input.market_pack !== "object") {
    throw new Error("market_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "secrets_stored=false · inventory_mutated=false",
    "purchase_executed=false · hosted=false · pdf_primary=false",
    "live_router_authorized=false · production_router_verdict=REJECT",
  ];

  const settings = composeSettingsAddModelInventory({
    ...input.settings,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings.notes.map((n) => `[settings] ${n}`));

  const market_pack = composeMarketplaceFreeCompetitionDrNdShadowSourceAttach({
    ...input.market_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...market_pack.notes.map((n) => `[market_pack] ${n}`));

  const title = requireNonEmpty(market_pack.title, "title");
  const account_id = requireNonEmpty(market_pack.account_id, "account_id");
  const session_id = requireNonEmpty(market_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    market_pack.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(market_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(market_pack.asset_id, "asset_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      settings.pack_ready === true &&
      market_pack.pack_ready === true &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      settings.live_router_authorized === false &&
      market_pack.purchase_executed === false &&
      market_pack.hosted === false &&
      market_pack.pdf_primary === false &&
      market_pack.live_dispatch_authorized === false &&
      market_pack.remote_fetched === false &&
      market_pack.backlog_mutated === false &&
      market_pack.live_router_authorized === false &&
      market_pack.twin_written === false &&
      market_pack.merge_executed === false &&
      market_pack.draft_written === false &&
      market_pack.secrets_stored === false &&
      market_pack.remote_index_queried === false &&
      market_pack.production_router_verdict === "REJECT" &&
      market_pack.competition_pack.nd_pack.nd_shadow
        .production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      market_pack.purchase_executed === false &&
      market_pack.hosted === false &&
      market_pack.production_router_verdict === "REJECT" &&
      (settings.pack_ready === true || market_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — settings add-model + marketplace free competition DR ND ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — settings, market_pack, or operator_ack gate open",
    );
  }

  if (
    settings.secrets_stored !== false ||
    settings.inventory_mutated !== false ||
    settings.live_router_authorized !== false ||
    market_pack.purchase_executed !== false ||
    market_pack.hosted !== false ||
    market_pack.pdf_primary !== false ||
    market_pack.live_dispatch_authorized !== false ||
    market_pack.remote_fetched !== false ||
    market_pack.backlog_mutated !== false ||
    market_pack.live_router_authorized !== false ||
    market_pack.twin_written !== false ||
    market_pack.merge_executed !== false ||
    market_pack.draft_written !== false ||
    market_pack.secrets_stored !== false ||
    market_pack.remote_index_queried !== false ||
    market_pack.production_router_verdict !== "REJECT" ||
    market_pack.competition_pack.nd_pack.nd_shadow
      .production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    title,
    account_id,
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    settings,
    market_pack,
    pack_ready,
    secrets_stored: false,
    inventory_mutated: false,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    live_meter_read: false,
    remote_index_queried: false,
    charge_executed: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "settings_add_model_marketplace_free_competition_dr_nd_compose_advisory",
  };
}

export function formatSettingsAddModelMarketplaceFreeCompetitionDrNdSummary(
  c: SettingsAddModelMarketplaceFreeCompetitionDrNdCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `settings_ready=${c.settings.pack_ready} · ` +
    `market_ready=${c.market_pack.pack_ready} · ` +
    `proposed_new=${c.settings.proposed_new_count} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `secrets_stored=false · inventory_mutated=false · purchase_executed=false`
  );
}
