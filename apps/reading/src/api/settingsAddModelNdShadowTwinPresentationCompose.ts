/**
 * Settings add-model inventory residual over ND shadow REJECT + recursive twin
 * presentation + competition DR source-attach pack (pure).
 *
 * Operator vision: add models in settings (BYOK ids only) with budget bar /
 * projection while working the ND twin presentation pack — never store secrets,
 * never mutate inventory, never live-route.
 *
 * secrets_stored / inventory_mutated always false.
 * live_router_authorized always false; production_router_verdict always REJECT.
 */

import {
  composeSettingsAddModelInventory,
  type SettingsAddModelInventoryCompose,
  type SettingsAddModelInventoryInput,
} from "./settingsAddModelInventoryCompose";
import {
  composeNdShadowTwinPresentationCompetitionDrSourceAttach,
  type NdShadowTwinPresentationCompetitionDrSourceAttachCompose,
  type NdShadowTwinPresentationCompetitionDrSourceAttachInput,
} from "./ndShadowTwinPresentationCompetitionDrSourceAttachCompose";

export interface SettingsAddModelNdShadowTwinPresentationInput {
  settings: Omit<SettingsAddModelInventoryInput, "operator_ack">;
  nd_pack: Omit<
    NdShadowTwinPresentationCompetitionDrSourceAttachInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SettingsAddModelNdShadowTwinPresentationCompose {
  parent_asset_id: string;
  session_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  settings: SettingsAddModelInventoryCompose;
  nd_pack: NdShadowTwinPresentationCompetitionDrSourceAttachCompose;
  pack_ready: boolean;
  secrets_stored: false;
  inventory_mutated: false;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  twin_written: false;
  remote_fetched: false;
  live_dispatch_authorized: false;
  live_execution_authorized: false;
  charge_executed: false;
  suite_rewritten: false;
  notes: string[];
  authority: "settings_add_model_nd_shadow_twin_presentation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Settings add-model inventory overlay on ND shadow twin presentation pack.
 * Never stores secrets; never mutates inventory; never live-routes.
 */
export function composeSettingsAddModelNdShadowTwinPresentation(
  input: SettingsAddModelNdShadowTwinPresentationInput,
): SettingsAddModelNdShadowTwinPresentationCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.settings || typeof input.settings !== "object") {
    throw new Error("settings must be an object");
  }
  if (!input.nd_pack || typeof input.nd_pack !== "object") {
    throw new Error("nd_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "secrets_stored=false · inventory_mutated=false",
    "draft_written=false · merge_executed=false · live_dispatched=false · pack_dispatched=false",
    "backlog_mutated=false · store_mutated=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const settings = composeSettingsAddModelInventory({
    ...input.settings,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings.notes.map((n) => `[settings] ${n}`));

  const nd_pack = composeNdShadowTwinPresentationCompetitionDrSourceAttach({
    ...input.nd_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...nd_pack.notes.map((n) => `[nd_pack] ${n}`));

  const parent_asset_id = requireNonEmpty(
    nd_pack.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(nd_pack.session_id, "session_id");
  const title = requireNonEmpty(nd_pack.title, "title");
  const account_id = requireNonEmpty(nd_pack.account_id, "account_id");
  const week_id = requireNonEmpty(nd_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(nd_pack.asset_id, "asset_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      settings.pack_ready === true &&
      nd_pack.pack_ready === true &&
      nd_pack.production_router_verdict === "REJECT" &&
      nd_pack.live_router_authorized === false &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      nd_pack.twin_written === false &&
      nd_pack.merge_executed === false &&
      nd_pack.purchase_executed === false &&
      nd_pack.remote_fetched === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      nd_pack.production_router_verdict === "REJECT" &&
      settings.secrets_stored === false &&
      (settings.pack_ready === true || nd_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — settings add-model + ND shadow twin presentation ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — settings, nd_pack, or operator_ack gate open",
    );
  }

  if (
    settings.secrets_stored !== false ||
    settings.inventory_mutated !== false ||
    settings.live_router_authorized !== false ||
    nd_pack.live_router_authorized !== false ||
    nd_pack.production_router_verdict !== "REJECT" ||
    nd_pack.twin_written !== false ||
    nd_pack.merge_executed !== false ||
    nd_pack.purchase_executed !== false ||
    nd_pack.remote_fetched !== false
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("purchase_executed=false");
  notes.push("twin_written=false");
  notes.push("remote_fetched=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("suite_rewritten=false");

  return {
    parent_asset_id,
    session_id,
    title,
    account_id,
    week_id,
    asset_id,
    settings,
    nd_pack,
    pack_ready,
    secrets_stored: false,
    inventory_mutated: false,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    twin_written: false,
    remote_fetched: false,
    live_dispatch_authorized: false,
    live_execution_authorized: false,
    charge_executed: false,
    suite_rewritten: false,
    notes,
    authority: "settings_add_model_nd_shadow_twin_presentation_compose_advisory",
  };
}

export function formatSettingsAddModelNdShadowTwinPresentationSummary(
  c: SettingsAddModelNdShadowTwinPresentationCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `settings_ready=${c.settings.pack_ready} · ` +
    `proposed_new=${c.settings.proposed_new_count} · ` +
    `nd_pack_ready=${c.nd_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `secrets_stored=false · inventory_mutated=false · live_router_authorized=false`
  );
}
