/**
 * Recursive twin note-taker over settings add-model fullscreen MO draft multi
 * pack (pure).
 *
 * Operator vision: every information asset has a twin document of insights and
 * questions (LLM as perfect note-taker), proposed here over the full research
 * workstation pack — settings model inventory, fullscreen DR, MO price ceiling,
 * draft multi-select — without writing twins or injecting live prompts.
 *
 * twin_written / prompts_injected / live_dispatch_authorized always false.
 * secrets_stored / inventory_mutated / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
  type RecursiveTwinNoteTakerInput,
} from "./recursiveTwinNoteTakerCompose";
import {
  composeSettingsAddModelFullscreenMoDraftMulti,
  type SettingsAddModelFullscreenMoDraftMultiCompose,
  type SettingsAddModelFullscreenMoDraftMultiInput,
} from "./settingsAddModelFullscreenMoDraftMultiCompose";

export interface RecursiveTwinSettingsFullscreenMoInput {
  twin: Omit<RecursiveTwinNoteTakerInput, "operator_ack">;
  settings_pack: Omit<
    SettingsAddModelFullscreenMoDraftMultiInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require twin.twin_propose_ready AND
   * settings_pack.pack_ready, and parent_asset_id alignment.
   */
  require_both?: boolean;
}

export interface RecursiveTwinSettingsFullscreenMoCompose {
  session_id: string;
  parent_asset_id: string;
  twin: RecursiveTwinNoteTakerCompose;
  settings_pack: SettingsAddModelFullscreenMoDraftMultiCompose;
  pack_ready: boolean;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  record_persisted: false;
  remote_index_queried: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  store_mutated: false;
  backlog_mutated: false;
  notes: string[];
  authority: "recursive_twin_settings_fullscreen_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Recursive twin note-taker stacked on settings fullscreen MO draft multi pack.
 * Never writes twins, stores secrets, or live-dispatches.
 */
export function composeRecursiveTwinSettingsFullscreenMo(
  input: RecursiveTwinSettingsFullscreenMoInput,
): RecursiveTwinSettingsFullscreenMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.twin || typeof input.twin !== "object") {
    throw new Error("twin must be an object");
  }
  if (!input.settings_pack || typeof input.settings_pack !== "object") {
    throw new Error("settings_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "twin_written=false · prompts_injected=false · live_dispatch_authorized=false",
    "secrets_stored=false · inventory_mutated=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const twin = composeRecursiveTwinNoteTaker({
    ...input.twin,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin.notes.map((n) => `[twin] ${n}`));

  const settings_pack = composeSettingsAddModelFullscreenMoDraftMulti({
    ...input.settings_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings_pack.notes.map((n) => `[settings_pack] ${n}`));

  const parent_asset_id = requireNonEmpty(
    twin.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(settings_pack.session_id, "session_id");

  const parent_aligned = settings_pack.parent_asset_id === parent_asset_id;
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between twin and settings_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      parent_aligned &&
      twin.twin_propose_ready === true &&
      settings_pack.pack_ready === true &&
      settings_pack.production_router_verdict === "REJECT" &&
      twin.twin_written === false &&
      twin.prompts_injected === false &&
      twin.live_dispatch_authorized === false &&
      settings_pack.secrets_stored === false &&
      settings_pack.inventory_mutated === false &&
      settings_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      parent_aligned &&
      input.operator_ack === true &&
      settings_pack.production_router_verdict === "REJECT" &&
      twin.twin_written === false &&
      (twin.twin_propose_ready === true || settings_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — recursive twin note-taker + settings fullscreen MO pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — twin, settings_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false ||
    settings_pack.secrets_stored !== false ||
    settings_pack.inventory_mutated !== false ||
    settings_pack.charge_executed !== false ||
    settings_pack.live_execution_authorized !== false ||
    settings_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("remote_index_queried=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("store_mutated=false");
  notes.push("backlog_mutated=false");

  return {
    session_id,
    parent_asset_id,
    twin,
    settings_pack,
    pack_ready,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    record_persisted: false,
    remote_index_queried: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    store_mutated: false,
    backlog_mutated: false,
    notes,
    authority: "recursive_twin_settings_fullscreen_mo_compose_advisory",
  };
}

export function formatRecursiveTwinSettingsFullscreenMoSummary(
  c: RecursiveTwinSettingsFullscreenMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `twin_propose_ready=${c.twin.twin_propose_ready} · ` +
    `settings_ready=${c.settings_pack.pack_ready} · ` +
    `focus_q=${c.twin.focus_question_count} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `twin_written=false · prompts_injected=false · secrets_stored=false`
  );
}
