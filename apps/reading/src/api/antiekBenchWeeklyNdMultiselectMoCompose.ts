/**
 * Antiek-bench weekly usage-learn + ND multi-select workstation MO pack (pure).
 *
 * Operator vision: recursive Antiek-bench learns what worked/didn't this week
 * and proposes sub-benchmark rewrites, while the full multi-select + ND shadow
 * REJECT research pack remains ready for model-quality decisions —
 * without mutating bench store or authorizing ND as production router.
 *
 * backlog_mutated / store_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeAntiekBenchWeeklyUsageLearn,
  type AntiekBenchWeeklyUsageLearnCompose,
  type AntiekBenchWeeklyUsageLearnInput,
} from "./antiekBenchWeeklyUsageLearnCompose";
import {
  composeNdShadowFloatingMultiselectWorkstationMo,
  type NdShadowFloatingMultiselectWorkstationMoCompose,
  type NdShadowFloatingMultiselectWorkstationMoInput,
} from "./ndShadowFloatingMultiselectWorkstationMoCompose";

export interface AntiekBenchWeeklyNdMultiselectMoInput {
  weekly_learn: Omit<AntiekBenchWeeklyUsageLearnInput, "operator_ack">;
  nd_research: Omit<
    NdShadowFloatingMultiselectWorkstationMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require weekly_learn.learn_ready AND
   * nd_research.pack_ready. When false, either path may ready the pack.
   */
  require_both?: boolean;
}

export interface AntiekBenchWeeklyNdMultiselectMoCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  weekly_learn: AntiekBenchWeeklyUsageLearnCompose;
  nd_research: NdShadowFloatingMultiselectWorkstationMoCompose;
  pack_ready: boolean;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  purchase_executed: false;
  twin_written: false;
  live_execution_authorized: false;
  notes: string[];
  authority: "antiek_bench_weekly_nd_multiselect_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose Antiek-bench weekly learn with ND multi-select research pack.
 * Never mutates bench backlog/store; never authorizes ND production router.
 */
export function composeAntiekBenchWeeklyNdMultiselectMo(
  input: AntiekBenchWeeklyNdMultiselectMoInput,
): AntiekBenchWeeklyNdMultiselectMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.weekly_learn || typeof input.weekly_learn !== "object") {
    throw new Error("weekly_learn must be an object");
  }
  if (!input.nd_research || typeof input.nd_research !== "object") {
    throw new Error("nd_research must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "backlog_mutated=false · store_mutated=false — bench rewrite proposals only",
    "production_router_verdict=REJECT · live_router_authorized=false",
    "live_dispatched=false · pack_dispatched=false · purchase_executed=false",
    "twin_written=false · live_execution_authorized=false",
  ];

  const weekly_learn = composeAntiekBenchWeeklyUsageLearn({
    ...input.weekly_learn,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_learn.notes.map((n) => `[weekly_learn] ${n}`));

  const nd_research = composeNdShadowFloatingMultiselectWorkstationMo({
    ...input.nd_research,
    operator_ack: input.operator_ack,
  });
  notes.push(...nd_research.notes.map((n) => `[nd_research] ${n}`));

  const week_id = requireNonEmpty(weekly_learn.week_id, "week_id");
  const session_id = requireNonEmpty(nd_research.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    nd_research.parent_asset_id,
    "parent_asset_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      weekly_learn.learn_ready === true &&
      nd_research.pack_ready === true &&
      nd_research.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      nd_research.production_router_verdict === "REJECT" &&
      (weekly_learn.learn_ready === true || nd_research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — weekly bench learn + ND multi-select research ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — weekly_learn, nd_research, or operator_ack gate open",
    );
  }

  if (
    weekly_learn.backlog_mutated !== false ||
    weekly_learn.store_mutated !== false ||
    nd_research.production_router_verdict !== "REJECT" ||
    nd_research.live_router_authorized !== false ||
    nd_research.live_dispatched !== false ||
    nd_research.purchase_executed !== false ||
    nd_research.live_execution_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("purchase_executed=false");
  notes.push("twin_written=false");
  notes.push("live_execution_authorized=false");

  return {
    week_id,
    session_id,
    parent_asset_id,
    weekly_learn,
    nd_research,
    pack_ready,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    purchase_executed: false,
    twin_written: false,
    live_execution_authorized: false,
    notes,
    authority: "antiek_bench_weekly_nd_multiselect_mo_compose_advisory",
  };
}

export function formatAntiekBenchWeeklyNdMultiselectMoSummary(
  c: AntiekBenchWeeklyNdMultiselectMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `learn_ready=${c.weekly_learn.learn_ready} · ` +
    `proposals=${c.weekly_learn.proposal_count} · ` +
    `nd_research_ready=${c.nd_research.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `backlog_mutated=false · store_mutated=false · ` +
    `live_router_authorized=false · live_execution_authorized=false`
  );
}
