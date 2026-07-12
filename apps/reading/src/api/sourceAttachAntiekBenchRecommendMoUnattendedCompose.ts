/**
 * HTML-native source attach (arxiv/substack) residual over Antiek-bench
 * recommend + MO unattended fullscreen draft multi-select pack (pure).
 *
 * Operator vision: call knowledge-dense publications into deep research while
 * weekly task→model recommendation and Midnight Oil unattended package remain
 * pure — every source HTML-native, never remote-fetched.
 *
 * remote_fetched always false.
 * pdf_view_authorized / pdf_primary always false.
 * suite_rewritten / live_router_authorized always false.
 * live_execution_authorized / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeHtmlNativeSourceAttach,
  type HtmlNativeSourceAttachCompose,
  type HtmlNativeSourceAttachInput,
} from "./htmlNativeSourceAttachCompose";
import {
  composeAntiekBenchRecommendMoUnattendedFullscreenDraft,
  type AntiekBenchRecommendMoUnattendedFullscreenDraftCompose,
  type AntiekBenchRecommendMoUnattendedFullscreenDraftInput,
} from "./antiekBenchRecommendMoUnattendedFullscreenDraftCompose";

export interface SourceAttachAntiekBenchRecommendMoUnattendedInput {
  sources: Omit<HtmlNativeSourceAttachInput, "operator_ack">;
  recommend_pack: Omit<
    AntiekBenchRecommendMoUnattendedFullscreenDraftInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require attach_ready AND recommend_pack.pack_ready,
   * session/parent alignment, and honesty gates.
   */
  require_both?: boolean;
}

export interface SourceAttachAntiekBenchRecommendMoUnattendedCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  week_id: string;
  focus_task: string;
  title: string;
  account_id: string;
  operator_id: string;
  sources: HtmlNativeSourceAttachCompose;
  recommend_pack: AntiekBenchRecommendMoUnattendedFullscreenDraftCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  attach_ready: boolean;
  remote_fetched: false;
  store_mutated: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  suite_rewritten: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
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
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  notes: string[];
  authority: "source_attach_antiek_bench_recommend_mo_unattended_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Source attach residual stacked on Antiek-bench recommend + MO unattended pack.
 * Never remote-fetches; never rewrites suite; never PDF-primary; ND REJECT.
 */
export function composeSourceAttachAntiekBenchRecommendMoUnattended(
  input: SourceAttachAntiekBenchRecommendMoUnattendedInput,
): SourceAttachAntiekBenchRecommendMoUnattendedCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.sources || typeof input.sources !== "object") {
    throw new Error("sources must be an object");
  }
  if (!input.recommend_pack || typeof input.recommend_pack !== "object") {
    throw new Error("recommend_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false — pure attach only (no live arxiv/substack)",
    "pdf_view_authorized=false · pdf_primary=false",
    "suite_rewritten=false · live_router_authorized=false",
    "live_execution_authorized=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const sources = composeHtmlNativeSourceAttach({
    ...input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...sources.notes.map((n) => `[sources] ${n}`));

  const recommend_pack = composeAntiekBenchRecommendMoUnattendedFullscreenDraft({
    ...input.recommend_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...recommend_pack.notes.map((n) => `[recommend_pack] ${n}`));

  const session_id = requireNonEmpty(sources.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    sources.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(recommend_pack.asset_id, "asset_id");
  const week_id = requireNonEmpty(recommend_pack.week_id, "week_id");
  const focus_task = requireNonEmpty(recommend_pack.focus_task, "focus_task");
  const title = requireNonEmpty(recommend_pack.title, "title");
  const account_id = requireNonEmpty(recommend_pack.account_id, "account_id");
  const operator_id = requireNonEmpty(recommend_pack.operator_id, "operator_id");

  const session_aligned = recommend_pack.session_id === session_id;
  const parent_aligned =
    recommend_pack.parent_asset_id === parent_asset_id ||
    recommend_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between sources and recommend_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between sources and recommend_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      sources.attach_ready === true &&
      recommend_pack.pack_ready === true &&
      sources.remote_fetched === false &&
      sources.pdf_view_authorized === false &&
      sources.store_mutated === false &&
      recommend_pack.suite_rewritten === false &&
      recommend_pack.live_router_authorized === false &&
      recommend_pack.secrets_stored === false &&
      recommend_pack.live_execution_authorized === false &&
      recommend_pack.charge_executed === false &&
      recommend_pack.production_router_verdict === "REJECT" &&
      recommend_pack.pdf_primary === false &&
      recommend_pack.remote_index_queried === false &&
      recommend_pack.purchase_executed === false &&
      recommend_pack.hosted === false &&
      recommend_pack.inventory_mutated === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      sources.remote_fetched === false &&
      sources.pdf_view_authorized === false &&
      recommend_pack.production_router_verdict === "REJECT" &&
      recommend_pack.pdf_primary === false &&
      recommend_pack.suite_rewritten === false &&
      (sources.attach_ready === true || recommend_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — source attach + Antiek-bench recommend MO unattended ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — sources, recommend_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    sources.remote_fetched !== false ||
    sources.pdf_view_authorized !== false ||
    sources.store_mutated !== false ||
    recommend_pack.suite_rewritten !== false ||
    recommend_pack.pdf_primary !== false ||
    recommend_pack.live_router_authorized !== false ||
    recommend_pack.secrets_stored !== false ||
    recommend_pack.live_execution_authorized !== false ||
    recommend_pack.charge_executed !== false ||
    recommend_pack.remote_index_queried !== false ||
    recommend_pack.purchase_executed !== false ||
    recommend_pack.hosted !== false ||
    recommend_pack.inventory_mutated !== false ||
    recommend_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("remote_fetched=false");
  notes.push("store_mutated=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("suite_rewritten=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
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
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");

  return {
    session_id,
    parent_asset_id,
    asset_id,
    week_id,
    focus_task,
    title,
    account_id,
    operator_id,
    sources,
    recommend_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    attach_ready: sources.attach_ready,
    remote_fetched: false,
    store_mutated: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    suite_rewritten: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
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
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    notes,
    authority:
      "source_attach_antiek_bench_recommend_mo_unattended_compose_advisory",
  };
}

export function formatSourceAttachAntiekBenchRecommendMoUnattendedSummary(
  c: SourceAttachAntiekBenchRecommendMoUnattendedCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `attach_ready=${c.attach_ready} · ` +
    `recommend_ready=${c.recommend_pack.pack_ready} · ` +
    `sources=${c.sources.source_count} · ` +
    `html_ready=${c.sources.html_ready_count} · ` +
    `focus=${c.focus_task} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_fetched=false · suite_rewritten=false · live_execution_authorized=false`
  );
}
