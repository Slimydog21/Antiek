/**
 * Midnight Oil unattended package residual over draft-before-merge floating
 * multi-select model decision ND twin pack (pure).
 *
 * Operator vision: set time + goals + price ceiling for unattended deep research
 * ("midnight oil") while the workstation holds draft-before-merge + multi-select
 * cohesive unit + model decision budget + twin search HTML-native ND twin —
 * without authorizing live workers.
 *
 * live_execution_authorized always false.
 * live_dispatched / merge_executed / draft_written always false.
 * live_router_authorized / secrets_stored / remote_index_queried always false.
 * production_router_verdict always REJECT.
 * approved_ceiling must meet recommended for mo pack_ready.
 */

import {
  composeMidnightOilUnattendedPackage,
  type MidnightOilUnattendedPackageCompose,
  type MidnightOilUnattendedPackageInput,
} from "./midnightOilUnattendedPackageCompose";
import {
  composeDraftBeforeMergeFloatingMultiselectModelDecisionNdTwin,
  type DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose,
  type DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinInput,
} from "./draftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose";

export interface MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinInput {
  mo: Omit<MidnightOilUnattendedPackageInput, "operator_ack">;
  draft_pack: Omit<
    DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  mo: MidnightOilUnattendedPackageCompose;
  draft_pack: DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * MO unattended package stacked on draft-before-merge floating multi-select ND twin.
 * Never live-executes; ND REJECT.
 */
export function composeMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwin(
  input: MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinInput,
): MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.draft_pack || typeof input.draft_pack !== "object") {
    throw new Error("draft_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false — unattended package never launches workers",
    "live_dispatched=false · merge_executed=false · draft_written=false",
    "live_router_authorized=false · secrets_stored=false · remote_index_queried=false",
    "production_router_verdict=REJECT",
  ];

  const mo = composeMidnightOilUnattendedPackage({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const draft_pack = composeDraftBeforeMergeFloatingMultiselectModelDecisionNdTwin({
    ...input.draft_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_pack.notes.map((n) => `[draft_pack] ${n}`));

  const session_id = requireNonEmpty(draft_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_pack.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(draft_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(draft_pack.asset_id, "asset_id");
  const title = requireNonEmpty(draft_pack.title, "title");
  const account_id = requireNonEmpty(draft_pack.account_id, "account_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.unattended_package_ready === true &&
      draft_pack.pack_ready === true &&
      mo.live_execution_authorized === false &&
      draft_pack.live_dispatched === false &&
      draft_pack.merge_executed === false &&
      draft_pack.draft_written === false &&
      draft_pack.live_router_authorized === false &&
      draft_pack.secrets_stored === false &&
      draft_pack.remote_index_queried === false &&
      draft_pack.pdf_primary === false &&
      draft_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      mo.live_execution_authorized === false &&
      draft_pack.production_router_verdict === "REJECT" &&
      draft_pack.pdf_primary === false &&
      (mo.unattended_package_ready === true || draft_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO unattended + draft-before-merge multiselect ND twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, draft_pack, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    draft_pack.live_dispatched !== false ||
    draft_pack.merge_executed !== false ||
    draft_pack.draft_written !== false ||
    draft_pack.live_router_authorized !== false ||
    draft_pack.secrets_stored !== false ||
    draft_pack.remote_index_queried !== false ||
    draft_pack.pdf_primary !== false ||
    draft_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_execution_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    mo,
    draft_pack,
    pack_ready,
    live_execution_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_advisory",
  };
}

export function formatMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinSummary(
  c: MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.unattended_package_ready} · ` +
    `draft_ready=${c.draft_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_execution_authorized=false · merge_executed=false · draft_written=false`
  );
}
