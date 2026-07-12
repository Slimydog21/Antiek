/**
 * Antiek-bench recursive rewrite residual over model decision-tree budget +
 * twin search + HTML-native recursive twin marketplace free pack (pure).
 *
 * Operator vision: weekly Antiek-bench learns from usage patterns (what
 * worked / didn't) and proposes sub-benchmark rewrites as the platform
 * expands — stacked on model driver selection with usage bar + projection,
 * twin intelligent search, HTML-native view, recursive twin note-taker, and
 * free-before-buy marketplace honesty.
 *
 * suite_rewritten / applied always false (proposal only).
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * remote_index_queried / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  proposeAntiekBenchRecursiveRewrite,
  type BenchRewriteProposal,
  type UsagePattern,
} from "./antiekBenchRecursiveRewrite";
import {
  composeModelDecisionTwinSearchHtmlNativeMarketplace,
  type ModelDecisionTwinSearchHtmlNativeMarketplaceCompose,
  type ModelDecisionTwinSearchHtmlNativeMarketplaceInput,
} from "./modelDecisionTwinSearchHtmlNativeMarketplaceCompose";

export interface AntiekBenchRewriteModelDecisionMarketplaceInput {
  /** Usage patterns that drive recursive rewrite proposals (never invented). */
  rewrite: {
    week_label: string;
    patterns: UsagePattern[];
  };
  model_decision_pack: Omit<
    ModelDecisionTwinSearchHtmlNativeMarketplaceInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require rewrite has ≥1 proposal AND
   * model_decision_pack.pack_ready.
   */
  require_both?: boolean;
  /**
   * When true (default), block pack if rewrite would apply production changes
   * (applied must remain false — honesty invariant).
   */
  block_if_applied?: boolean;
}

export interface AntiekBenchRewriteModelDecisionMarketplaceCompose {
  week_id: string;
  week_label: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  focus_task: string;
  rewrite: BenchRewriteProposal;
  model_decision_pack: ModelDecisionTwinSearchHtmlNativeMarketplaceCompose;
  proposal_count: number;
  pack_ready: boolean;
  /** Always false — proposal only; production bench never rewritten. */
  suite_rewritten: false;
  /** Always false — mirrors rewrite.applied. */
  applied: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "antiek_bench_rewrite_model_decision_marketplace_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Antiek-bench recursive rewrite residual stacked on model-decision
 * twin-search HTML-native marketplace pack.
 * Never rewrites suite; never live-routes; never PDF-primary; ND REJECT.
 */
export function composeAntiekBenchRewriteModelDecisionMarketplace(
  input: AntiekBenchRewriteModelDecisionMarketplaceInput,
): AntiekBenchRewriteModelDecisionMarketplaceCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.rewrite || typeof input.rewrite !== "object") {
    throw new Error("rewrite must be an object");
  }
  if (
    !input.model_decision_pack ||
    typeof input.model_decision_pack !== "object"
  ) {
    throw new Error("model_decision_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }
  const block_if_applied =
    input.block_if_applied === undefined ? true : input.block_if_applied;
  if (typeof block_if_applied !== "boolean") {
    throw new Error("block_if_applied must be boolean when set");
  }

  const notes: string[] = [
    "suite_rewritten=false · applied=false — rewrite proposal only",
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "remote_index_queried=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const rewrite = proposeAntiekBenchRecursiveRewrite({
    week_label: input.rewrite.week_label,
    patterns: input.rewrite.patterns,
  });
  notes.push(...rewrite.notes.map((n) => `[rewrite] ${n}`));

  if (rewrite.applied !== false) {
    throw new Error("invariant: rewrite.applied must be false");
  }

  const model_decision_pack = composeModelDecisionTwinSearchHtmlNativeMarketplace(
    {
      ...input.model_decision_pack,
      operator_ack: input.operator_ack,
    },
  );
  notes.push(
    ...model_decision_pack.notes.map((n) => `[model_decision_pack] ${n}`),
  );

  const week_label = requireNonEmpty(rewrite.week_label, "week_label");
  const week_id = requireNonEmpty(model_decision_pack.week_id, "week_id");
  const session_id = requireNonEmpty(
    model_decision_pack.session_id,
    "session_id",
  );
  const asset_id = requireNonEmpty(model_decision_pack.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    model_decision_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(model_decision_pack.title, "title");
  const account_id = requireNonEmpty(
    model_decision_pack.account_id,
    "account_id",
  );
  const focus_task = requireNonEmpty(
    model_decision_pack.focus_task,
    "focus_task",
  );

  const proposal_count = rewrite.proposals.length;
  const rewrite_ready = proposal_count >= 1;
  const applied_ok = !block_if_applied || rewrite.applied === false;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      rewrite_ready &&
      applied_ok &&
      model_decision_pack.pack_ready === true &&
      model_decision_pack.suite_rewritten === false &&
      model_decision_pack.live_router_authorized === false &&
      model_decision_pack.secrets_stored === false &&
      model_decision_pack.live_meter_read === false &&
      model_decision_pack.remote_index_queried === false &&
      model_decision_pack.pdf_primary === false &&
      model_decision_pack.pdf_view_authorized === false &&
      model_decision_pack.twin_written === false &&
      model_decision_pack.purchase_executed === false &&
      model_decision_pack.hosted === false &&
      model_decision_pack.inventory_mutated === false &&
      model_decision_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      applied_ok &&
      model_decision_pack.live_router_authorized === false &&
      model_decision_pack.suite_rewritten === false &&
      model_decision_pack.production_router_verdict === "REJECT" &&
      model_decision_pack.pdf_primary === false &&
      (rewrite_ready || model_decision_pack.pack_ready === true);
  }

  if (!rewrite_ready && require_both) {
    notes.push(
      "rewrite has zero proposals — pack_ready blocked (need fail/mixed usage signal)",
    );
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — Antiek-bench rewrite residual + model decision marketplace ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — rewrite, model_decision_pack, or operator_ack gate open",
    );
  }

  if (
    rewrite.applied !== false ||
    model_decision_pack.suite_rewritten !== false ||
    model_decision_pack.live_router_authorized !== false ||
    model_decision_pack.secrets_stored !== false ||
    model_decision_pack.live_meter_read !== false ||
    model_decision_pack.remote_index_queried !== false ||
    model_decision_pack.pdf_primary !== false ||
    model_decision_pack.pdf_view_authorized !== false ||
    model_decision_pack.twin_written !== false ||
    model_decision_pack.purchase_executed !== false ||
    model_decision_pack.hosted !== false ||
    model_decision_pack.inventory_mutated !== false ||
    model_decision_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("suite_rewritten=false");
  notes.push("applied=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    week_label,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    focus_task,
    rewrite,
    model_decision_pack,
    proposal_count,
    pack_ready,
    suite_rewritten: false,
    applied: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "antiek_bench_rewrite_model_decision_marketplace_compose_advisory",
  };
}

export function formatAntiekBenchRewriteModelDecisionMarketplaceSummary(
  c: AntiekBenchRewriteModelDecisionMarketplaceCompose,
): string {
  const budget =
    c.model_decision_pack.decision.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${c.model_decision_pack.decision.would_exceed}`;
  return (
    `pack_ready=${c.pack_ready} · ` +
    `proposals=${c.proposal_count} · applied=false · suite_rewritten=false · ` +
    `decision_ready=${c.model_decision_pack.decision.decision_ready} · ` +
    `model=${c.model_decision_pack.decision.driver.decision.selected_model_id} · ` +
    `${budget} · ` +
    `hits=${c.model_decision_pack.twin_search_pack.hit_count} · ` +
    `week=${c.week_label} · task=${c.focus_task} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · secrets_stored=false · remote_index_queried=false`
  );
}
