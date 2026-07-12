/**
 * Highlight float DR launch → twin intelligent search competition pack (pure).
 *
 * Operator vision: from a reading/research highlight, spin up a floating deep
 * research instance, then engage twin intelligent search over the competition
 * DR + ND shadow REJECT + weekly marketplace substrate — same HTML surface for
 * reading and research. Never live-dispatches, remote-indexes, or writes twins.
 *
 * live_dispatched / live_dispatch_authorized / remote_fetched always false.
 * remote_index_queried / merge_executed / twin_written always false.
 * production_router_verdict always REJECT.
 */

import {
  composeHighlightDeepResearchLaunch,
  type HighlightDeepResearchLaunchCompose,
  type HighlightDeepResearchLaunchInput,
} from "./highlightDeepResearchLaunchCompose";
import {
  composeTwinSearchCompetitionDrNdShadowWeeklyMarketplace,
  type TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose,
  type TwinSearchCompetitionDrNdShadowWeeklyMarketplaceInput,
} from "./twinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose";

export interface HighlightFloatTwinSearchCompetitionInput {
  highlight: Omit<HighlightDeepResearchLaunchInput, "operator_ack">;
  twin_search_pack: Omit<
    TwinSearchCompetitionDrNdShadowWeeklyMarketplaceInput,
    "operator_ack" | "search_query"
  > & {
    /** When omitted and seed_search_from_highlight, uses highlight text. */
    search_query?: string | null;
  };
  operator_ack: boolean;
  /**
   * When true (default), seed twin_search_pack.search_query from highlight
   * text when search_query is empty/omitted.
   */
  seed_search_from_highlight?: boolean;
  require_both?: boolean;
}

export interface HighlightFloatTwinSearchCompetitionCompose {
  session_id: string;
  parent_asset_id: string;
  highlight_launch: HighlightDeepResearchLaunchCompose;
  twin_search_pack: TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose;
  pack_ready: boolean;
  live_dispatched: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  remote_index_queried: false;
  merge_executed: false;
  twin_written: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  store_mutated: false;
  purchase_executed: false;
  hosted: false;
  backlog_mutated: false;
  pack_dispatched: false;
  notes: string[];
  authority: "highlight_float_twin_search_competition_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Highlight float DR launch stacked on twin search competition ND weekly pack.
 * Never dispatches live workers or indexes remotes.
 */
export function composeHighlightFloatTwinSearchCompetition(
  input: HighlightFloatTwinSearchCompetitionInput,
): HighlightFloatTwinSearchCompetitionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.highlight || typeof input.highlight !== "object") {
    throw new Error("highlight must be an object");
  }
  if (!input.twin_search_pack || typeof input.twin_search_pack !== "object") {
    throw new Error("twin_search_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }
  const seed =
    input.seed_search_from_highlight === undefined
      ? true
      : input.seed_search_from_highlight;
  if (typeof seed !== "boolean") {
    throw new Error("seed_search_from_highlight must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · live_dispatch_authorized=false · remote_fetched=false",
    "remote_index_queried=false · merge_executed=false · twin_written=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const highlight_launch = composeHighlightDeepResearchLaunch({
    ...input.highlight,
    operator_ack: input.operator_ack,
  });
  notes.push(...highlight_launch.notes.map((n) => `[highlight_launch] ${n}`));

  let search_query =
    input.twin_search_pack.search_query != null &&
    String(input.twin_search_pack.search_query).trim()
      ? String(input.twin_search_pack.search_query).trim()
      : "";
  if (!search_query && seed) {
    search_query = requireNonEmpty(input.highlight.highlight, "highlight");
    notes.push("search_query seeded from highlight text");
  }
  if (!search_query) {
    throw new Error(
      "search_query must be non-empty (or enable seed_search_from_highlight)",
    );
  }

  const twin_search_pack = composeTwinSearchCompetitionDrNdShadowWeeklyMarketplace(
    {
      competition_pack: input.twin_search_pack.competition_pack,
      search_query,
      extra_twin_records: input.twin_search_pack.extra_twin_records,
      search_limit: input.twin_search_pack.search_limit,
      min_parents_for_merge: input.twin_search_pack.min_parents_for_merge,
      search_pack_id: input.twin_search_pack.search_pack_id,
      require_both: input.twin_search_pack.require_both,
      operator_ack: input.operator_ack,
    },
  );
  notes.push(
    ...twin_search_pack.notes.map((n) => `[twin_search_pack] ${n}`),
  );

  const parent_asset_id = requireNonEmpty(
    highlight_launch.instance.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(
    twin_search_pack.session_id,
    "session_id",
  );

  const parent_aligned =
    twin_search_pack.parent_asset_id === parent_asset_id;
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between highlight and twin_search_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      parent_aligned &&
      highlight_launch.launch_ready === true &&
      twin_search_pack.pack_ready === true &&
      twin_search_pack.production_router_verdict === "REJECT" &&
      highlight_launch.live_dispatched === false &&
      twin_search_pack.remote_index_queried === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      parent_aligned &&
      input.operator_ack === true &&
      twin_search_pack.production_router_verdict === "REJECT" &&
      (highlight_launch.launch_ready === true ||
        twin_search_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — highlight float launch + twin search competition pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — highlight_launch, twin_search_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    highlight_launch.live_dispatched !== false ||
    highlight_launch.merge_executed !== false ||
    twin_search_pack.live_dispatch_authorized !== false ||
    twin_search_pack.remote_fetched !== false ||
    twin_search_pack.remote_index_queried !== false ||
    twin_search_pack.merge_executed !== false ||
    twin_search_pack.twin_written !== false ||
    twin_search_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("remote_index_queried=false");
  notes.push("merge_executed=false");
  notes.push("twin_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("store_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("backlog_mutated=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    parent_asset_id,
    highlight_launch,
    twin_search_pack,
    pack_ready,
    live_dispatched: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    remote_index_queried: false,
    merge_executed: false,
    twin_written: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    store_mutated: false,
    purchase_executed: false,
    hosted: false,
    backlog_mutated: false,
    pack_dispatched: false,
    notes,
    authority: "highlight_float_twin_search_competition_compose_advisory",
  };
}

export function formatHighlightFloatTwinSearchCompetitionSummary(
  c: HighlightFloatTwinSearchCompetitionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `launch_ready=${c.highlight_launch.launch_ready} · ` +
    `twin_search_ready=${c.twin_search_pack.pack_ready} · ` +
    `hits=${c.twin_search_pack.twin_search.search.hits.length} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · remote_index_queried=false · twin_written=false`
  );
}
