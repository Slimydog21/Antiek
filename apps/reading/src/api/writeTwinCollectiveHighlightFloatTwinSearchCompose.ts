/**
 * Write twin collective analysis over highlight-float twin-search competition
 * pack (pure).
 *
 * Operator vision: after highlight→float DR + twin intelligent search over
 * competition/ND weekly substrate, fold twin slices + chase findings into a
 * provisional write draft and collective written analysis — without writing
 * assets or live-dispatching.
 *
 * draft_written / analysis_written / merge_executed always false.
 * live_dispatched / remote_index_queried / twin_written always false.
 * production_router_verdict always REJECT.
 */

import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
  type WriteModeTwinCollectiveAnalysisInput,
} from "./writeModeTwinCollectiveAnalysisCompose";
import {
  composeHighlightFloatTwinSearchCompetition,
  type HighlightFloatTwinSearchCompetitionCompose,
  type HighlightFloatTwinSearchCompetitionInput,
} from "./highlightFloatTwinSearchCompetitionCompose";

export interface WriteTwinCollectiveHighlightFloatTwinSearchInput {
  write: Omit<WriteModeTwinCollectiveAnalysisInput, "operator_ack">;
  highlight_pack: Omit<
    HighlightFloatTwinSearchCompetitionInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface WriteTwinCollectiveHighlightFloatTwinSearchCompose {
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  write: WriteModeTwinCollectiveAnalysisCompose;
  highlight_pack: HighlightFloatTwinSearchCompetitionCompose;
  pack_ready: boolean;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  store_mutated: false;
  live_dispatched: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  remote_index_queried: false;
  twin_written: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  hosted: false;
  backlog_mutated: false;
  pack_dispatched: false;
  notes: string[];
  authority: "write_twin_collective_highlight_float_twin_search_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Write twin collective analysis stacked on highlight-float twin-search pack.
 * Never writes drafts/analysis; never live-dispatches or remote-indexes.
 */
export function composeWriteTwinCollectiveHighlightFloatTwinSearch(
  input: WriteTwinCollectiveHighlightFloatTwinSearchInput,
): WriteTwinCollectiveHighlightFloatTwinSearchCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.write || typeof input.write !== "object") {
    throw new Error("write must be an object");
  }
  if (!input.highlight_pack || typeof input.highlight_pack !== "object") {
    throw new Error("highlight_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false · analysis_written=false · merge_executed=false",
    "live_dispatched=false · remote_index_queried=false · twin_written=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const write = composeWriteModeTwinCollectiveAnalysis({
    ...input.write,
    operator_ack: input.operator_ack,
  });
  notes.push(...write.notes.map((n) => `[write] ${n}`));

  const highlight_pack = composeHighlightFloatTwinSearchCompetition({
    ...input.highlight_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...highlight_pack.notes.map((n) => `[highlight_pack] ${n}`));

  const session_id = requireNonEmpty(write.session_id, "session_id");
  const draft_id = requireNonEmpty(write.draft_id, "draft_id");
  const parent_asset_id = requireNonEmpty(
    write.parent_asset_id,
    "parent_asset_id",
  );

  const session_aligned = highlight_pack.session_id === session_id;
  const parent_aligned = highlight_pack.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between write and highlight_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between write and highlight_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      write.pack_ready === true &&
      highlight_pack.pack_ready === true &&
      highlight_pack.production_router_verdict === "REJECT" &&
      write.draft_written === false &&
      write.analysis_written === false &&
      highlight_pack.remote_index_queried === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      highlight_pack.production_router_verdict === "REJECT" &&
      (write.pack_ready === true || highlight_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — write twin collective + highlight float twin-search ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — write, highlight_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    write.draft_written !== false ||
    write.analysis_written !== false ||
    write.merge_executed !== false ||
    write.store_mutated !== false ||
    write.live_dispatched !== false ||
    highlight_pack.live_dispatched !== false ||
    highlight_pack.remote_index_queried !== false ||
    highlight_pack.twin_written !== false ||
    highlight_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("backlog_mutated=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    draft_id,
    parent_asset_id,
    write,
    highlight_pack,
    pack_ready,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    store_mutated: false,
    live_dispatched: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    remote_index_queried: false,
    twin_written: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    hosted: false,
    backlog_mutated: false,
    pack_dispatched: false,
    notes,
    authority:
      "write_twin_collective_highlight_float_twin_search_compose_advisory",
  };
}

export function formatWriteTwinCollectiveHighlightFloatTwinSearchSummary(
  c: WriteTwinCollectiveHighlightFloatTwinSearchCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `write_ready=${c.write.pack_ready} · ` +
    `highlight_ready=${c.highlight_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · analysis_written=false · remote_index_queried=false`
  );
}
