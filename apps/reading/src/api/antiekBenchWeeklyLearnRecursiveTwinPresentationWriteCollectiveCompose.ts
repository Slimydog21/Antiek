/**
 * Antiek-bench weekly usage-learn residual over recursive twin presentation +
 * write twin collective fullscreen Midnight Oil unattended ND twin pack (pure).
 *
 * Operator vision: surface weekly bench learn (what worked / failed → rewrite
 * proposals) beside recursive twin presentation + write collective + fullscreen
 * + MO unattended + draft multiselect ND twin so settings / decision-tree
 * consumers see learn readiness with the full honesty stack — without mutating
 * bench backlog or store.
 *
 * backlog_mutated / store_mutated / suite_rewritten always false.
 * twin_written / merge_executed / draft_written always false.
 * live_router_authorized / secrets_stored always false.
 * production_router_verdict always REJECT.
 */

import {
  composeAntiekBenchWeeklyUsageLearn,
  type AntiekBenchWeeklyUsageLearnCompose,
  type AntiekBenchWeeklyUsageLearnInput,
} from "./antiekBenchWeeklyUsageLearnCompose";
import {
  composeRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwin,
  type RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose,
  type RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinInput,
} from "./recursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose";

export interface AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveInput {
  weekly_learn: Omit<AntiekBenchWeeklyUsageLearnInput, "operator_ack">;
  twin_presentation_pack: Omit<
    RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  weekly_learn: AntiekBenchWeeklyUsageLearnCompose;
  twin_presentation_pack: RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose;
  pack_ready: boolean;
  learn_ready: boolean;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  inventory_mutated: false;
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  live_dispatch_authorized: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Weekly bench learn stacked on recursive twin presentation write collective pack.
 * Never mutates bench; never writes twin; ND REJECT.
 */
export function composeAntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollective(
  input: AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveInput,
): AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.weekly_learn || typeof input.weekly_learn !== "object") {
    throw new Error("weekly_learn must be an object");
  }
  if (
    !input.twin_presentation_pack ||
    typeof input.twin_presentation_pack !== "object"
  ) {
    throw new Error("twin_presentation_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
    "twin_written=false · merge_executed=false · draft_written=false",
    "live_router_authorized=false · secrets_stored=false",
    "production_router_verdict=REJECT",
  ];

  const weekly_learn = composeAntiekBenchWeeklyUsageLearn({
    ...input.weekly_learn,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_learn.notes.map((n) => `[weekly_learn] ${n}`));

  const twin_presentation_pack =
    composeRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwin({
      ...input.twin_presentation_pack,
      operator_ack: input.operator_ack,
    });
  notes.push(
    ...twin_presentation_pack.notes.map((n) => `[twin_presentation_pack] ${n}`),
  );

  const week_id = requireNonEmpty(weekly_learn.week_id, "week_id");
  const session_id = requireNonEmpty(
    twin_presentation_pack.session_id,
    "session_id",
  );
  const parent_asset_id = requireNonEmpty(
    twin_presentation_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(
    twin_presentation_pack.asset_id,
    "asset_id",
  );
  const title = requireNonEmpty(twin_presentation_pack.title, "title");
  const account_id = requireNonEmpty(
    twin_presentation_pack.account_id,
    "account_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      weekly_learn.learn_ready === true &&
      twin_presentation_pack.pack_ready === true &&
      weekly_learn.backlog_mutated === false &&
      weekly_learn.store_mutated === false &&
      twin_presentation_pack.twin_written === false &&
      twin_presentation_pack.merge_executed === false &&
      twin_presentation_pack.draft_written === false &&
      twin_presentation_pack.analysis_written === false &&
      twin_presentation_pack.live_dispatched === false &&
      twin_presentation_pack.live_execution_authorized === false &&
      twin_presentation_pack.live_router_authorized === false &&
      twin_presentation_pack.secrets_stored === false &&
      twin_presentation_pack.remote_index_queried === false &&
      twin_presentation_pack.pdf_primary === false &&
      twin_presentation_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      weekly_learn.backlog_mutated === false &&
      weekly_learn.store_mutated === false &&
      twin_presentation_pack.production_router_verdict === "REJECT" &&
      twin_presentation_pack.pdf_primary === false &&
      twin_presentation_pack.twin_written === false &&
      (weekly_learn.learn_ready === true ||
        twin_presentation_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — weekly bench learn + recursive twin presentation write collective ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — weekly_learn, twin_presentation_pack, or operator_ack gate open",
    );
  }

  if (
    weekly_learn.backlog_mutated !== false ||
    weekly_learn.store_mutated !== false ||
    twin_presentation_pack.twin_written !== false ||
    twin_presentation_pack.merge_executed !== false ||
    twin_presentation_pack.draft_written !== false ||
    twin_presentation_pack.analysis_written !== false ||
    twin_presentation_pack.live_dispatched !== false ||
    twin_presentation_pack.live_execution_authorized !== false ||
    twin_presentation_pack.live_router_authorized !== false ||
    twin_presentation_pack.secrets_stored !== false ||
    twin_presentation_pack.remote_index_queried !== false ||
    twin_presentation_pack.pdf_primary !== false ||
    twin_presentation_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("inventory_mutated=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    weekly_learn,
    twin_presentation_pack,
    pack_ready,
    learn_ready: weekly_learn.learn_ready,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    inventory_mutated: false,
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    live_dispatch_authorized: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_advisory",
  };
}

export function formatAntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveSummary(
  c: AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `learn_ready=${c.learn_ready} · ` +
    `proposals=${c.weekly_learn.proposal_count} · ` +
    `twin_presentation_ready=${c.twin_presentation_pack.pack_ready} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `backlog_mutated=false · twin_written=false · suite_rewritten=false`
  );
}
