/**
 * Midnight Oil unattended package over fullscreen + draft-before-merge
 * collective presented twins pack (pure).
 *
 * Operator vision: set time + goals + price ceiling for unattended deep
 * research while the workstation holds fullscreen draft + collective twin
 * presentation — without authorizing live workers.
 *
 * live_execution_authorized always false.
 * live_dispatched / merge_executed / draft_written / purchase_executed false.
 * production_router_verdict always REJECT.
 */

import {
  composeMidnightOilUnattendedPackage,
  type MidnightOilUnattendedPackageCompose,
  type MidnightOilUnattendedPackageInput,
} from "./midnightOilUnattendedPackageCompose";
import {
  composeFullscreenDraftCollectivePresentedTwins,
  type FullscreenDraftCollectivePresentedTwinsCompose,
  type FullscreenDraftCollectivePresentedTwinsInput,
} from "./fullscreenDraftCollectivePresentedTwinsCompose";

export interface MoUnattendedFullscreenDraftCollectiveInput {
  mo: Omit<MidnightOilUnattendedPackageInput, "operator_ack">;
  fullscreen_pack: Omit<
    FullscreenDraftCollectivePresentedTwinsInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MoUnattendedFullscreenDraftCollectiveCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  mo: MidnightOilUnattendedPackageCompose;
  fullscreen_pack: FullscreenDraftCollectivePresentedTwinsCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_router_authorized: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  secrets_stored: false;
  live_meter_read: false;
  store_mutated: false;
  suite_rewritten: false;
  remote_index_queried: false;
  inventory_mutated: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "mo_unattended_fullscreen_draft_collective_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * MO unattended package stacked on fullscreen draft collective pack.
 * Never live-executes; never purchases; ND REJECT.
 */
export function composeMoUnattendedFullscreenDraftCollective(
  input: MoUnattendedFullscreenDraftCollectiveInput,
): MoUnattendedFullscreenDraftCollectiveCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.fullscreen_pack || typeof input.fullscreen_pack !== "object") {
    throw new Error("fullscreen_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false — unattended package never launches workers",
    "live_dispatched=false · merge_executed=false · draft_written=false",
    "purchase_executed=false · production_router_verdict=REJECT",
  ];

  const mo = composeMidnightOilUnattendedPackage({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const fullscreen_pack = composeFullscreenDraftCollectivePresentedTwins({
    ...input.fullscreen_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(
    ...fullscreen_pack.notes.map((n) => `[fullscreen_pack] ${n}`),
  );

  const session_id = requireNonEmpty(
    fullscreen_pack.session_id,
    "session_id",
  );
  const parent_asset_id = requireNonEmpty(
    fullscreen_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(fullscreen_pack.title, "title");
  const account_id = requireNonEmpty(fullscreen_pack.account_id, "account_id");
  const week_id = requireNonEmpty(fullscreen_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(fullscreen_pack.asset_id, "asset_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.unattended_package_ready === true &&
      fullscreen_pack.pack_ready === true &&
      mo.live_execution_authorized === false &&
      fullscreen_pack.live_dispatched === false &&
      fullscreen_pack.merge_executed === false &&
      fullscreen_pack.draft_written === false &&
      fullscreen_pack.purchase_executed === false &&
      fullscreen_pack.live_router_authorized === false &&
      fullscreen_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      mo.live_execution_authorized === false &&
      fullscreen_pack.purchase_executed === false &&
      fullscreen_pack.production_router_verdict === "REJECT" &&
      (mo.unattended_package_ready === true ||
        fullscreen_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO unattended + fullscreen draft collective ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, fullscreen_pack, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    fullscreen_pack.live_dispatched !== false ||
    fullscreen_pack.merge_executed !== false ||
    fullscreen_pack.draft_written !== false ||
    fullscreen_pack.purchase_executed !== false ||
    fullscreen_pack.live_router_authorized !== false ||
    fullscreen_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_execution_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_router_authorized=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("remote_index_queried=false");
  notes.push("inventory_mutated=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    title,
    account_id,
    week_id,
    asset_id,
    mo,
    fullscreen_pack,
    pack_ready,
    live_execution_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_router_authorized: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    secrets_stored: false,
    live_meter_read: false,
    store_mutated: false,
    suite_rewritten: false,
    remote_index_queried: false,
    inventory_mutated: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "mo_unattended_fullscreen_draft_collective_compose_advisory",
  };
}

export function formatMoUnattendedFullscreenDraftCollectiveSummary(
  c: MoUnattendedFullscreenDraftCollectiveCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.unattended_package_ready} · ` +
    `fullscreen_ready=${c.fullscreen_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_execution_authorized=false · merge_executed=false · purchase_executed=false`
  );
}
