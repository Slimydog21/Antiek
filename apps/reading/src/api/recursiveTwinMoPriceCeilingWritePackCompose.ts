/**
 * Recursive twin note-taker + MO price-ceiling write pack (pure).
 *
 * Operator vision: every information asset has a twin of insights/questions;
 * bind twin proposal onto the MO price-ceiling + write twin settings draft pack
 * so recursive note-taking informs the full research workstation without live
 * twin write or MO launch.
 *
 * twin_written / prompts_injected / live_dispatch_authorized always false.
 * charge_executed / live_execution_authorized always false.
 * draft_written / analysis_written / merge_executed always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
  type RecursiveTwinNoteTakerInput,
} from "./recursiveTwinNoteTakerCompose";
import {
  composeMoPriceCeilingWriteTwinSettingsDraft,
  type MoPriceCeilingWriteTwinSettingsDraftCompose,
  type MoPriceCeilingWriteTwinSettingsDraftInput,
} from "./moPriceCeilingWriteTwinSettingsDraftCompose";

export interface RecursiveTwinMoPriceCeilingWritePackInput {
  twin: Omit<RecursiveTwinNoteTakerInput, "operator_ack">;
  mo_write: Omit<MoPriceCeilingWriteTwinSettingsDraftInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface RecursiveTwinMoPriceCeilingWritePackCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  twin: RecursiveTwinNoteTakerCompose;
  mo_write: MoPriceCeilingWriteTwinSettingsDraftCompose;
  pack_ready: boolean;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  charge_executed: false;
  live_execution_authorized: false;
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
  notes: string[];
  authority: "recursive_twin_mo_price_ceiling_write_pack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Recursive twin note-taker bind on MO price-ceiling write pack.
 * Never writes twin; never injects prompts; never charges or launches MO.
 */
export function composeRecursiveTwinMoPriceCeilingWritePack(
  input: RecursiveTwinMoPriceCeilingWritePackInput,
): RecursiveTwinMoPriceCeilingWritePackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.twin || typeof input.twin !== "object") {
    throw new Error("twin must be an object");
  }
  if (!input.mo_write || typeof input.mo_write !== "object") {
    throw new Error("mo_write must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "twin_written=false · prompts_injected=false · live_dispatch_authorized=false",
    "charge_executed=false · live_execution_authorized=false",
    "draft_written=false · analysis_written=false · merge_executed=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const twin = composeRecursiveTwinNoteTaker({
    ...input.twin,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin.notes.map((n) => `[twin] ${n}`));

  const mo_write = composeMoPriceCeilingWriteTwinSettingsDraft({
    ...input.mo_write,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_write.notes.map((n) => `[mo_write] ${n}`));

  const session_id = requireNonEmpty(mo_write.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    twin.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(mo_write.week_id, "week_id");

  const aligned = mo_write.parent_asset_id === parent_asset_id;
  if (!aligned) {
    notes.push(
      "parent_asset_id mismatch between twin and mo_write — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      aligned &&
      twin.twin_propose_ready === true &&
      mo_write.pack_ready === true &&
      mo_write.production_router_verdict === "REJECT" &&
      twin.twin_written === false &&
      mo_write.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      mo_write.production_router_verdict === "REJECT" &&
      twin.twin_written === false &&
      (twin.twin_propose_ready === true || mo_write.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — recursive twin + MO price-ceiling write pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — twin, mo_write, alignment, or operator_ack gate open",
    );
  }

  if (
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false ||
    mo_write.charge_executed !== false ||
    mo_write.live_execution_authorized !== false ||
    mo_write.draft_written !== false ||
    mo_write.analysis_written !== false ||
    mo_write.merge_executed !== false ||
    mo_write.production_router_verdict !== "REJECT" ||
    mo_write.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
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

  return {
    session_id,
    parent_asset_id,
    week_id,
    twin,
    mo_write,
    pack_ready,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    charge_executed: false,
    live_execution_authorized: false,
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
    notes,
    authority: "recursive_twin_mo_price_ceiling_write_pack_compose_advisory",
  };
}

export function formatRecursiveTwinMoPriceCeilingWritePackSummary(
  c: RecursiveTwinMoPriceCeilingWritePackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `twin_propose_ready=${c.twin.twin_propose_ready} · ` +
    `mo_write_ready=${c.mo_write.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `twin_written=false · charge_executed=false · live_dispatch_authorized=false`
  );
}
