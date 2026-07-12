/**
 * arxiv/substack source publication DR attach residual over Antiek-bench
 * weekly learn + recursive twin presentation write collective pack (pure).
 *
 * Operator vision: call arxiv, substack, and other knowledge-dense publications
 * into deep research as HTML-native refs with citation + quality gates, while
 * weekly bench learn + recursive twin presentation + write collective +
 * fullscreen + Midnight Oil unattended ND twin honesty remain pure — never
 * live-fetches, mutates bench, or writes twins.
 *
 * remote_fetched / live_dispatch_authorized always false.
 * backlog_mutated / store_mutated / suite_rewritten always false.
 * twin_written / merge_executed / draft_written always false.
 * pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  composeSourcePublicationDrAttachQuality,
  type SourcePublicationDrAttachQualityCompose,
  type SourcePublicationDrAttachQualityInput,
} from "./sourcePublicationDrAttachQualityCompose";
import {
  composeAntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollective,
  type AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose,
  type AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveInput,
} from "./antiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose";

export interface SourceAttachAntiekBenchWeeklyLearnTwinPresentationInput {
  sources: Omit<SourcePublicationDrAttachQualityInput, "operator_ack">;
  weekly_pack: Omit<
    AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  sources: SourcePublicationDrAttachQualityCompose;
  weekly_pack: AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  remote_fetched: false;
  live_dispatch_authorized: false;
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
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "source_attach_antiek_bench_weekly_learn_twin_presentation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * arxiv/substack HTML attach + quality on Antiek-bench weekly learn twin presentation pack.
 * Never remote-fetches; never mutates bench; ND REJECT.
 */
export function composeSourceAttachAntiekBenchWeeklyLearnTwinPresentation(
  input: SourceAttachAntiekBenchWeeklyLearnTwinPresentationInput,
): SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.sources || typeof input.sources !== "object") {
    throw new Error("sources must be an object");
  }
  if (!input.weekly_pack || typeof input.weekly_pack !== "object") {
    throw new Error("weekly_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false · live_dispatch_authorized=false",
    "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
    "twin_written=false · merge_executed=false · draft_written=false",
    "pdf_primary=false · production_router_verdict=REJECT",
  ];

  const sources = composeSourcePublicationDrAttachQuality({
    ...input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...sources.notes.map((n) => `[sources] ${n}`));

  const weekly_pack =
    composeAntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollective({
      ...input.weekly_pack,
      operator_ack: input.operator_ack,
    });
  notes.push(...weekly_pack.notes.map((n) => `[weekly_pack] ${n}`));

  const session_id = requireNonEmpty(sources.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    sources.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(weekly_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(weekly_pack.asset_id, "asset_id");
  const title = requireNonEmpty(weekly_pack.title, "title");
  const account_id = requireNonEmpty(weekly_pack.account_id, "account_id");

  const session_aligned = weekly_pack.session_id === session_id;
  const parent_aligned =
    weekly_pack.parent_asset_id === parent_asset_id ||
    weekly_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between sources and weekly_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between sources and weekly_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      sources.pack_ready === true &&
      weekly_pack.pack_ready === true &&
      sources.remote_fetched === false &&
      sources.live_dispatch_authorized === false &&
      sources.pdf_view_authorized === false &&
      sources.store_mutated === false &&
      weekly_pack.backlog_mutated === false &&
      weekly_pack.store_mutated === false &&
      weekly_pack.suite_rewritten === false &&
      weekly_pack.twin_written === false &&
      weekly_pack.merge_executed === false &&
      weekly_pack.draft_written === false &&
      weekly_pack.live_dispatched === false &&
      weekly_pack.live_router_authorized === false &&
      weekly_pack.secrets_stored === false &&
      weekly_pack.remote_index_queried === false &&
      weekly_pack.pdf_primary === false &&
      weekly_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      sources.remote_fetched === false &&
      weekly_pack.production_router_verdict === "REJECT" &&
      weekly_pack.pdf_primary === false &&
      (sources.pack_ready === true || weekly_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — arxiv/substack attach + weekly learn twin presentation ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — sources, weekly_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    sources.remote_fetched !== false ||
    sources.live_dispatch_authorized !== false ||
    sources.pdf_view_authorized !== false ||
    sources.store_mutated !== false ||
    weekly_pack.backlog_mutated !== false ||
    weekly_pack.store_mutated !== false ||
    weekly_pack.suite_rewritten !== false ||
    weekly_pack.twin_written !== false ||
    weekly_pack.merge_executed !== false ||
    weekly_pack.draft_written !== false ||
    weekly_pack.live_dispatched !== false ||
    weekly_pack.live_router_authorized !== false ||
    weekly_pack.secrets_stored !== false ||
    weekly_pack.remote_index_queried !== false ||
    weekly_pack.pdf_primary !== false ||
    weekly_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("remote_fetched=false");
  notes.push("live_dispatch_authorized=false");
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
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    sources,
    weekly_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    remote_fetched: false,
    live_dispatch_authorized: false,
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
    production_router_verdict: "REJECT",
    notes,
    authority:
      "source_attach_antiek_bench_weekly_learn_twin_presentation_compose_advisory",
  };
}

export function formatSourceAttachAntiekBenchWeeklyLearnTwinPresentationSummary(
  c: SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `sources_ready=${c.sources.pack_ready} · ` +
    `weekly_ready=${c.weekly_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_fetched=false · backlog_mutated=false · twin_written=false`
  );
}
