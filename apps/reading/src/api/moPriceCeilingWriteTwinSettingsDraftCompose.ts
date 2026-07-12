/**
 * Midnight Oil price-ceiling + write twin collective settings draft pack (pure).
 *
 * Operator vision: unattended midnight-oil with recommended price ceiling,
 * stacked on write twin collective analysis over settings draft fullscreen ND
 * pack — never live-executes MO; never writes analysis/draft; never charges.
 *
 * live_execution_authorized / charge_executed always false.
 * draft_written / analysis_written / merge_executed always false.
 * secrets_stored / inventory_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeMidnightOilPriceCeilingApproval,
  type MidnightOilPriceCeilingApprovalCompose,
  type MidnightOilPriceCeilingApprovalInput,
} from "./midnightOilPriceCeilingApprovalCompose";
import {
  composeWriteTwinCollectiveSettingsDraftFullscreenNdMo,
  type WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose,
  type WriteTwinCollectiveSettingsDraftFullscreenNdMoInput,
} from "./writeTwinCollectiveSettingsDraftFullscreenNdMoCompose";

export interface MoPriceCeilingWriteTwinSettingsDraftInput {
  mo: Omit<MidnightOilPriceCeilingApprovalInput, "operator_ack">;
  research_write: Omit<
    WriteTwinCollectiveSettingsDraftFullscreenNdMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MoPriceCeilingWriteTwinSettingsDraftCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  operator_id: string;
  mo: MidnightOilPriceCeilingApprovalCompose;
  research_write: WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  charge_executed: false;
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
  notes: string[];
  authority: "mo_price_ceiling_write_twin_settings_draft_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * MO price-ceiling overlay on write twin settings draft fullscreen ND pack.
 * Never live-executes MO; never charges; never writes analysis/draft.
 */
export function composeMoPriceCeilingWriteTwinSettingsDraft(
  input: MoPriceCeilingWriteTwinSettingsDraftInput,
): MoPriceCeilingWriteTwinSettingsDraftCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.research_write || typeof input.research_write !== "object") {
    throw new Error("research_write must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false · charge_executed=false",
    "draft_written=false · analysis_written=false · merge_executed=false",
    "secrets_stored=false · inventory_mutated=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const mo = composeMidnightOilPriceCeilingApproval({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const research_write = composeWriteTwinCollectiveSettingsDraftFullscreenNdMo(
    {
      ...input.research_write,
      operator_ack: input.operator_ack,
    },
  );
  notes.push(...research_write.notes.map((n) => `[research_write] ${n}`));

  const session_id = requireNonEmpty(research_write.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    research_write.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(research_write.week_id, "week_id");
  const operator_id = requireNonEmpty(mo.operator_id, "operator_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.pack_ready === true &&
      research_write.pack_ready === true &&
      research_write.production_router_verdict === "REJECT" &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      research_write.production_router_verdict === "REJECT" &&
      mo.charge_executed === false &&
      (mo.pack_ready === true || research_write.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO price-ceiling + write twin settings draft ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, research_write, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    mo.charge_executed !== false ||
    research_write.draft_written !== false ||
    research_write.analysis_written !== false ||
    research_write.merge_executed !== false ||
    research_write.secrets_stored !== false ||
    research_write.inventory_mutated !== false ||
    research_write.production_router_verdict !== "REJECT" ||
    research_write.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
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

  return {
    session_id,
    parent_asset_id,
    week_id,
    operator_id,
    mo,
    research_write,
    pack_ready,
    live_execution_authorized: false,
    charge_executed: false,
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
    notes,
    authority: "mo_price_ceiling_write_twin_settings_draft_compose_advisory",
  };
}

export function formatMoPriceCeilingWriteTwinSettingsDraftSummary(
  c: MoPriceCeilingWriteTwinSettingsDraftCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.pack_ready} · ` +
    `ceiling_approved=${c.mo.ceiling_approved} · ` +
    `research_write_ready=${c.research_write.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `charge_executed=false · live_execution_authorized=false`
  );
}
