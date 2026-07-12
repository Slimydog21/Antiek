/**
 * Write-mode twin collective analysis + settings draft fullscreen weekly ND (pure).
 *
 * Operator vision: after floating multi-agent research on the draft+fullscreen
 * pack, merge twin substrate + completed chases into written analysis while
 * settings add-model inventory remains available — never writes analysis/draft,
 * never mutates inventory, never live-routes.
 *
 * draft_written / analysis_written / merge_executed always false.
 * secrets_stored / inventory_mutated always false.
 * live_dispatched / pack_dispatched / backlog_mutated / store_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
  type WriteModeTwinCollectiveAnalysisInput,
} from "./writeModeTwinCollectiveAnalysisCompose";
import {
  composeSettingsAddModelDraftFullscreenWeeklyNdMo,
  type SettingsAddModelDraftFullscreenWeeklyNdMoCompose,
  type SettingsAddModelDraftFullscreenWeeklyNdMoInput,
} from "./settingsAddModelDraftFullscreenWeeklyNdMoCompose";

export interface WriteTwinCollectiveSettingsDraftFullscreenNdMoInput {
  write: Omit<WriteModeTwinCollectiveAnalysisInput, "operator_ack">;
  settings_research: Omit<
    SettingsAddModelDraftFullscreenWeeklyNdMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  write: WriteModeTwinCollectiveAnalysisCompose;
  settings_research: SettingsAddModelDraftFullscreenWeeklyNdMoCompose;
  pack_ready: boolean;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  secrets_stored: false;
  inventory_mutated: false;
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
  authority: "write_twin_collective_settings_draft_fullscreen_nd_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose write twin collective analysis with settings draft fullscreen weekly ND.
 * Never writes analysis/draft; never mutates settings inventory; ND REJECT.
 */
export function composeWriteTwinCollectiveSettingsDraftFullscreenNdMo(
  input: WriteTwinCollectiveSettingsDraftFullscreenNdMoInput,
): WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.write || typeof input.write !== "object") {
    throw new Error("write must be an object");
  }
  if (!input.settings_research || typeof input.settings_research !== "object") {
    throw new Error("settings_research must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false · analysis_written=false · merge_executed=false",
    "secrets_stored=false · inventory_mutated=false",
    "live_dispatched=false · pack_dispatched=false · backlog_mutated=false · store_mutated=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const write = composeWriteModeTwinCollectiveAnalysis({
    ...input.write,
    operator_ack: input.operator_ack,
  });
  notes.push(...write.notes.map((n) => `[write] ${n}`));

  const settings_research = composeSettingsAddModelDraftFullscreenWeeklyNdMo({
    ...input.settings_research,
    operator_ack: input.operator_ack,
  });
  notes.push(
    ...settings_research.notes.map((n) => `[settings_research] ${n}`),
  );

  const session_id = requireNonEmpty(write.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    write.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(settings_research.week_id, "week_id");

  const aligned =
    settings_research.session_id === session_id &&
    settings_research.parent_asset_id === parent_asset_id;
  if (!aligned) {
    notes.push(
      "session/parent mismatch between write and settings_research — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      aligned &&
      write.pack_ready === true &&
      settings_research.pack_ready === true &&
      settings_research.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      settings_research.production_router_verdict === "REJECT" &&
      (write.pack_ready === true || settings_research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — write twin collective + settings draft fullscreen ND ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — write, settings_research, alignment, or operator_ack gate open",
    );
  }

  if (
    write.draft_written !== false ||
    write.analysis_written !== false ||
    write.merge_executed !== false ||
    write.store_mutated !== false ||
    write.live_dispatched !== false ||
    settings_research.secrets_stored !== false ||
    settings_research.inventory_mutated !== false ||
    settings_research.draft_written !== false ||
    settings_research.merge_executed !== false ||
    settings_research.live_dispatched !== false ||
    settings_research.production_router_verdict !== "REJECT" ||
    settings_research.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
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
    write,
    settings_research,
    pack_ready,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    secrets_stored: false,
    inventory_mutated: false,
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
      "write_twin_collective_settings_draft_fullscreen_nd_mo_compose_advisory",
  };
}

export function formatWriteTwinCollectiveSettingsDraftFullscreenNdMoSummary(
  c: WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `write_ready=${c.write.pack_ready} · ` +
    `settings_research_ready=${c.settings_research.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `analysis_written=false · draft_written=false · merge_executed=false`
  );
}
