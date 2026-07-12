/**
 * Settings add-model inventory over fullscreen MO price-ceiling draft multi
 * pack (pure).
 *
 * Operator vision: add models in settings (BYOK honesty, usage bar, projection)
 * while fullscreen DR + midnight-oil price ceiling + draft multi-select research
 * pack remain pure — never stores secrets or mutates inventory live.
 *
 * secrets_stored / inventory_mutated always false.
 * live_dispatched / charge_executed / live_execution_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeSettingsAddModelInventory,
  type SettingsAddModelInventoryCompose,
  type SettingsAddModelInventoryInput,
} from "./settingsAddModelInventoryCompose";
import {
  composeFullscreenMoPriceCeilingDraftMulti,
  type FullscreenMoPriceCeilingDraftMultiCompose,
  type FullscreenMoPriceCeilingDraftMultiInput,
} from "./fullscreenMoPriceCeilingDraftMultiCompose";

export interface SettingsAddModelFullscreenMoDraftMultiInput {
  settings: Omit<SettingsAddModelInventoryInput, "operator_ack">;
  fullscreen_mo: Omit<
    FullscreenMoPriceCeilingDraftMultiInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SettingsAddModelFullscreenMoDraftMultiCompose {
  session_id: string;
  parent_asset_id: string;
  settings: SettingsAddModelInventoryCompose;
  fullscreen_mo: FullscreenMoPriceCeilingDraftMultiCompose;
  pack_ready: boolean;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  prompts_injected: false;
  record_persisted: false;
  remote_index_queried: false;
  twin_written: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  store_mutated: false;
  backlog_mutated: false;
  notes: string[];
  authority: "settings_add_model_fullscreen_mo_draft_multi_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Settings add-model inventory stacked on fullscreen MO draft multi pack.
 * Never stores secrets or mutates inventory.
 */
export function composeSettingsAddModelFullscreenMoDraftMulti(
  input: SettingsAddModelFullscreenMoDraftMultiInput,
): SettingsAddModelFullscreenMoDraftMultiCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.settings || typeof input.settings !== "object") {
    throw new Error("settings must be an object");
  }
  if (!input.fullscreen_mo || typeof input.fullscreen_mo !== "object") {
    throw new Error("fullscreen_mo must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
    "live_dispatched=false · charge_executed=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const settings = composeSettingsAddModelInventory({
    ...input.settings,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings.notes.map((n) => `[settings] ${n}`));

  const fullscreen_mo = composeFullscreenMoPriceCeilingDraftMulti({
    ...input.fullscreen_mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen_mo.notes.map((n) => `[fullscreen_mo] ${n}`));

  const session_id = requireNonEmpty(fullscreen_mo.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen_mo.parent_asset_id,
    "parent_asset_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      settings.pack_ready === true &&
      fullscreen_mo.pack_ready === true &&
      fullscreen_mo.production_router_verdict === "REJECT" &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      settings.live_router_authorized === false &&
      fullscreen_mo.live_dispatched === false &&
      fullscreen_mo.charge_executed === false &&
      fullscreen_mo.live_execution_authorized === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      fullscreen_mo.production_router_verdict === "REJECT" &&
      settings.secrets_stored === false &&
      (settings.pack_ready === true || fullscreen_mo.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — settings add-model + fullscreen MO draft multi ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — settings, fullscreen_mo, or operator_ack gate open",
    );
  }

  if (
    settings.secrets_stored !== false ||
    settings.inventory_mutated !== false ||
    settings.live_router_authorized !== false ||
    fullscreen_mo.live_dispatched !== false ||
    fullscreen_mo.charge_executed !== false ||
    fullscreen_mo.live_execution_authorized !== false ||
    fullscreen_mo.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("prompts_injected=false");
  notes.push("record_persisted=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("store_mutated=false");
  notes.push("backlog_mutated=false");

  return {
    session_id,
    parent_asset_id,
    settings,
    fullscreen_mo,
    pack_ready,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    prompts_injected: false,
    record_persisted: false,
    remote_index_queried: false,
    twin_written: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    store_mutated: false,
    backlog_mutated: false,
    notes,
    authority:
      "settings_add_model_fullscreen_mo_draft_multi_compose_advisory",
  };
}

export function formatSettingsAddModelFullscreenMoDraftMultiSummary(
  c: SettingsAddModelFullscreenMoDraftMultiCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `settings_ready=${c.settings.pack_ready} · ` +
    `proposed_new=${c.settings.proposed_new_count} · ` +
    `fullscreen_mo_ready=${c.fullscreen_mo.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `secrets_stored=false · inventory_mutated=false · charge_executed=false`
  );
}
