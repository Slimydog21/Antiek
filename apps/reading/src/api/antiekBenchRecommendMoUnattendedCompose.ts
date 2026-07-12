/**
 * Antiek-bench task→model recommendation over Midnight Oil unattended +
 * source attach model decision pack (pure).
 *
 * Operator vision: weekly usage learn surfaces which models are best for
 * which tasks into the decision tree, while MO unattended (time+goals+
 * price ceiling) + arxiv/substack attach remain pure — never auto-routes.
 *
 * live_router_authorized always false.
 * suite_rewritten / backlog_mutated / store_mutated always false.
 * live_execution_authorized / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeAntiekBenchTaskModelRecommendation,
  type AntiekBenchTaskModelRecommendationCompose,
  type AntiekBenchTaskModelRecommendationInput,
} from "./antiekBenchTaskModelRecommendationCompose";
import {
  composeMoUnattendedSourceAttachModelDecision,
  type MoUnattendedSourceAttachModelDecisionCompose,
  type MoUnattendedSourceAttachModelDecisionInput,
} from "./moUnattendedSourceAttachModelDecisionCompose";

export interface AntiekBenchRecommendMoUnattendedInput {
  bench: Omit<AntiekBenchTaskModelRecommendationInput, "operator_ack">;
  mo_pack: Omit<MoUnattendedSourceAttachModelDecisionInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require bench.pack_ready AND mo_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface AntiekBenchRecommendMoUnattendedCompose {
  week_id: string;
  focus_task: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  operator_id: string;
  bench: AntiekBenchTaskModelRecommendationCompose;
  mo_pack: MoUnattendedSourceAttachModelDecisionCompose;
  pack_ready: boolean;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_fetched: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  notes: string[];
  authority: "antiek_bench_recommend_mo_unattended_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Antiek-bench task→model rec stacked on MO unattended source-attach pack.
 * Never live-routes; never rewrites suite; never charges.
 */
export function composeAntiekBenchRecommendMoUnattended(
  input: AntiekBenchRecommendMoUnattendedInput,
): AntiekBenchRecommendMoUnattendedCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.bench || typeof input.bench !== "object") {
    throw new Error("bench must be an object");
  }
  if (!input.mo_pack || typeof input.mo_pack !== "object") {
    throw new Error("mo_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_router_authorized=false — bench recommendation advisory only",
    "suite_rewritten=false · backlog_mutated=false · store_mutated=false",
    "live_execution_authorized=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const bench = composeAntiekBenchTaskModelRecommendation({
    ...input.bench,
    operator_ack: input.operator_ack,
  });
  notes.push(...bench.notes.map((n) => `[bench] ${n}`));

  const mo_pack = composeMoUnattendedSourceAttachModelDecision({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const week_id = requireNonEmpty(bench.week_id, "week_id");
  const focus_task = requireNonEmpty(bench.focus_task, "focus_task");
  const session_id = requireNonEmpty(mo_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    mo_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(mo_pack.asset_id, "asset_id");
  const operator_id = requireNonEmpty(mo_pack.operator_id, "operator_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      bench.pack_ready === true &&
      mo_pack.pack_ready === true &&
      bench.live_router_authorized === false &&
      bench.suite_rewritten === false &&
      bench.backlog_mutated === false &&
      bench.store_mutated === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.charge_executed === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      mo_pack.pdf_primary === false &&
      mo_pack.remote_fetched === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      bench.live_router_authorized === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      (bench.pack_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — Antiek-bench recommend + MO unattended pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — bench, mo_pack, or operator_ack gate open",
    );
  }

  if (
    bench.live_router_authorized !== false ||
    bench.secrets_stored !== false ||
    bench.suite_rewritten !== false ||
    bench.backlog_mutated !== false ||
    bench.store_mutated !== false ||
    mo_pack.live_execution_authorized !== false ||
    mo_pack.charge_executed !== false ||
    mo_pack.remote_fetched !== false ||
    mo_pack.pdf_primary !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");

  return {
    week_id,
    focus_task,
    session_id,
    parent_asset_id,
    asset_id,
    operator_id,
    bench,
    mo_pack,
    pack_ready,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_fetched: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    notes,
    authority: "antiek_bench_recommend_mo_unattended_compose_advisory",
  };
}

export function formatAntiekBenchRecommendMoUnattendedSummary(
  c: AntiekBenchRecommendMoUnattendedCompose,
): string {
  const rec = c.bench.recommendation?.recommended_model_id ?? "none";
  return (
    `pack_ready=${c.pack_ready} · ` +
    `bench_ready=${c.bench.pack_ready} · ` +
    `mo_ready=${c.mo_pack.pack_ready} · ` +
    `focus=${c.focus_task} · ` +
    `rec=${rec} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · suite_rewritten=false · live_execution_authorized=false`
  );
}
