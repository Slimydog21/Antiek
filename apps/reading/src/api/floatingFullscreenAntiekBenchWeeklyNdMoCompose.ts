/**
 * Floating fullscreen-open + Antiek-bench weekly ND multi-select pack (pure).
 *
 * Operator vision: open a floating deep-research instance fullscreen while the
 * weekly bench-learn + ND multi-select research pack remains ready — reading
 * and research share one HTML surface without live dispatch or bench mutation.
 *
 * live_dispatched / merge_executed / pack_dispatched always false.
 * backlog_mutated / store_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeFloatingFullscreenOpen,
  type FloatingFullscreenOpenCompose,
  type FloatingFullscreenOpenInput,
} from "./floatingFullscreenOpenCompose";
import {
  composeAntiekBenchWeeklyNdMultiselectMo,
  type AntiekBenchWeeklyNdMultiselectMoCompose,
  type AntiekBenchWeeklyNdMultiselectMoInput,
} from "./antiekBenchWeeklyNdMultiselectMoCompose";

export interface FloatingFullscreenAntiekBenchWeeklyNdMoInput {
  fullscreen: Omit<FloatingFullscreenOpenInput, "operator_ack">;
  weekly_nd: Omit<AntiekBenchWeeklyNdMultiselectMoInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FloatingFullscreenAntiekBenchWeeklyNdMoCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  fullscreen: FloatingFullscreenOpenCompose;
  weekly_nd: AntiekBenchWeeklyNdMultiselectMoCompose;
  pack_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  twin_written: false;
  live_execution_authorized: false;
  notes: string[];
  authority: "floating_fullscreen_antiek_bench_weekly_nd_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose floating fullscreen-open with weekly bench + ND multi-select pack.
 * Never live-dispatches; never mutates bench store; ND never production router.
 */
export function composeFloatingFullscreenAntiekBenchWeeklyNdMo(
  input: FloatingFullscreenAntiekBenchWeeklyNdMoInput,
): FloatingFullscreenAntiekBenchWeeklyNdMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.fullscreen || typeof input.fullscreen !== "object") {
    throw new Error("fullscreen must be an object");
  }
  if (!input.weekly_nd || typeof input.weekly_nd !== "object") {
    throw new Error("weekly_nd must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · merge_executed=false · pack_dispatched=false",
    "backlog_mutated=false · store_mutated=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
    "purchase_executed=false · twin_written=false · live_execution_authorized=false",
  ];

  const fullscreen = composeFloatingFullscreenOpen({
    ...input.fullscreen,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen.notes.map((n) => `[fullscreen] ${n}`));

  const weekly_nd = composeAntiekBenchWeeklyNdMultiselectMo({
    ...input.weekly_nd,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_nd.notes.map((n) => `[weekly_nd] ${n}`));

  const session_id = requireNonEmpty(fullscreen.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(weekly_nd.week_id, "week_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      fullscreen.fullscreen_ready === true &&
      weekly_nd.pack_ready === true &&
      weekly_nd.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      weekly_nd.production_router_verdict === "REJECT" &&
      (fullscreen.fullscreen_ready === true || weekly_nd.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — fullscreen float + weekly ND multi-select ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — fullscreen, weekly_nd, or operator_ack gate open",
    );
  }

  if (
    fullscreen.live_dispatched !== false ||
    fullscreen.merge_executed !== false ||
    fullscreen.pack_dispatched !== false ||
    weekly_nd.backlog_mutated !== false ||
    weekly_nd.store_mutated !== false ||
    weekly_nd.production_router_verdict !== "REJECT" ||
    weekly_nd.live_router_authorized !== false ||
    weekly_nd.live_dispatched !== false ||
    weekly_nd.live_execution_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
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
    fullscreen,
    weekly_nd,
    pack_ready,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    twin_written: false,
    live_execution_authorized: false,
    notes,
    authority: "floating_fullscreen_antiek_bench_weekly_nd_mo_compose_advisory",
  };
}

export function formatFloatingFullscreenAntiekBenchWeeklyNdMoSummary(
  c: FloatingFullscreenAntiekBenchWeeklyNdMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen.fullscreen_ready} · ` +
    `weekly_nd_ready=${c.weekly_nd.pack_ready} · ` +
    `proposals=${c.weekly_nd.weekly_learn.proposal_count} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · backlog_mutated=false · live_router_authorized=false`
  );
}
