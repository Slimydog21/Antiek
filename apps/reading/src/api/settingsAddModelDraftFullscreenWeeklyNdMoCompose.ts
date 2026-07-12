/**
 * Settings add-model inventory + draft-before-full-merge fullscreen weekly ND (pure).
 *
 * Operator vision: while working the draft+fullscreen research pack, add models
 * in settings (BYOK ids only), see budget bar / projection — never store secrets,
 * never mutate inventory, never live-route or merge.
 *
 * secrets_stored / inventory_mutated always false.
 * draft_written / merge_executed / live_dispatched / pack_dispatched always false.
 * backlog_mutated / store_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeSettingsAddModelInventory,
  type SettingsAddModelInventoryCompose,
  type SettingsAddModelInventoryInput,
} from "./settingsAddModelInventoryCompose";
import {
  composeFloatingDraftBeforeFullMergeFullscreenWeeklyNdMo,
  type FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose,
  type FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoInput,
} from "./floatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose";

export interface SettingsAddModelDraftFullscreenWeeklyNdMoInput {
  settings: Omit<SettingsAddModelInventoryInput, "operator_ack">;
  research_pack: Omit<
    FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SettingsAddModelDraftFullscreenWeeklyNdMoCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  settings: SettingsAddModelInventoryCompose;
  research_pack: FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose;
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
  live_execution_authorized: false;
  notes: string[];
  authority: "settings_add_model_draft_fullscreen_weekly_nd_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Settings add-model inventory overlay on draft+fullscreen weekly ND pack.
 * Never stores secrets; never mutates inventory; never merges or live-routes.
 */
export function composeSettingsAddModelDraftFullscreenWeeklyNdMo(
  input: SettingsAddModelDraftFullscreenWeeklyNdMoInput,
): SettingsAddModelDraftFullscreenWeeklyNdMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.settings || typeof input.settings !== "object") {
    throw new Error("settings must be an object");
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

  const research_pack = composeFloatingDraftBeforeFullMergeFullscreenWeeklyNdMo(
    {
      ...input.research_pack,
      operator_ack: input.operator_ack,
    },
  );
  notes.push(...research_pack.notes.map((n) => `[research_pack] ${n}`));

  const session_id = requireNonEmpty(research_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    research_pack.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(research_pack.week_id, "week_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      settings.pack_ready === true &&
      research_pack.pack_ready === true &&
      research_pack.production_router_verdict === "REJECT" &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      research_pack.production_router_verdict === "REJECT" &&
      settings.secrets_stored === false &&
      (settings.pack_ready === true || research_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — settings add-model + draft fullscreen weekly ND ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — settings, research_pack, or operator_ack gate open",
    );
  }

  if (
    settings.secrets_stored !== false ||
    settings.inventory_mutated !== false ||
    settings.live_router_authorized !== false ||
    research_pack.draft_written !== false ||
    research_pack.merge_executed !== false ||
    research_pack.live_dispatched !== false ||
    research_pack.pack_dispatched !== false ||
    research_pack.backlog_mutated !== false ||
    research_pack.store_mutated !== false ||
    research_pack.production_router_verdict !== "REJECT" ||
    research_pack.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
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
  notes.push("live_execution_authorized=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    settings,
    research_pack,
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
    live_execution_authorized: false,
    notes,
    authority:
      "settings_add_model_draft_fullscreen_weekly_nd_mo_compose_advisory",
  };
}

export function formatSettingsAddModelDraftFullscreenWeeklyNdMoSummary(
  c: SettingsAddModelDraftFullscreenWeeklyNdMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `settings_ready=${c.settings.pack_ready} · ` +
    `proposed_new=${c.settings.proposed_new_count} · ` +
    `research_ready=${c.research_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `secrets_stored=false · inventory_mutated=false · merge_executed=false`
  );
}
