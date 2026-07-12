/**
 * HTML-native view session + competition quality write → twin search (pure).
 *
 * Operator vision: competition-informed DR quality pack and twin substrate
 * search are human-viewable only as HTML — never PDF primary — on the
 * infinite information platform workstation.
 *
 * pdf_view_authorized / pdf_primary always false.
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * draft_written / analysis_written / merge_executed always false.
 * remote_index_queried / twin_written / store_mutated always false.
 */

import {
  composeHtmlNativeViewSessionAuthority,
  type HtmlNativeViewSessionAuthorityCompose,
  type HtmlNativeViewSessionAuthorityInput,
} from "./htmlNativeViewSessionAuthorityCompose";
import {
  composeCompetitionDrQualityWriteTwinSearch,
  type CompetitionDrQualityWriteTwinSearchCompose,
  type CompetitionDrQualityWriteTwinSearchInput,
} from "./competitionDrQualityWriteTwinSearchCompose";

export interface HtmlNativeCompetitionWriteTwinSearchInput {
  session_id: string;
  asset_id: string;
  html_projection_sha: string | null;
  view_requested: boolean;
  twin_bound: boolean;
  twin_substrate_ready?: boolean;
  claimed_format?: string | null;
  reading?: HtmlNativeViewSessionAuthorityInput["reading"];
  research?: HtmlNativeViewSessionAuthorityInput["research"];
  /** Competition quality write + twin search inputs (minus session_id). */
  competition: Omit<CompetitionDrQualityWriteTwinSearchInput, "session_id">;
  operator_ack: boolean;
  /**
   * When true (default), require html_view.pack_ready AND
   * competition_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface HtmlNativeCompetitionWriteTwinSearchCompose {
  session_id: string;
  asset_id: string;
  html_view: HtmlNativeViewSessionAuthorityCompose;
  competition_pack: CompetitionDrQualityWriteTwinSearchCompose;
  pack_ready: boolean;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  remote_index_queried: false;
  twin_written: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "html_native_competition_write_twin_search_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose HTML-native view authority with competition quality write→twin search.
 * Never PDF-authorizes; never dispatches/indexes/writes.
 */
export function composeHtmlNativeCompetitionWriteTwinSearch(
  input: HtmlNativeCompetitionWriteTwinSearchInput,
): HtmlNativeCompetitionWriteTwinSearchCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition || typeof input.competition !== "object") {
    throw new Error("competition must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "pdf_view_authorized=false · pdf_primary=false — HTML-native doctrine",
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "draft_written=false · analysis_written=false · merge_executed=false",
    "remote_index_queried=false · twin_written=false · store_mutated=false",
    "live_dispatched=false",
  ];

  const html_view = composeHtmlNativeViewSessionAuthority({
    session_id,
    asset_id,
    html_projection_sha: input.html_projection_sha,
    view_requested: input.view_requested,
    twin_bound: input.twin_bound,
    twin_substrate_ready: input.twin_substrate_ready,
    claimed_format: input.claimed_format,
    reading: input.reading,
    research: input.research,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_view.notes.map((n) => `[html_view] ${n}`));

  const competition_pack = composeCompetitionDrQualityWriteTwinSearch({
    ...input.competition,
    session_id,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition_pack.notes.map((n) => `[competition_pack] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      html_view.pack_ready === true &&
      competition_pack.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (html_view.pack_ready === true || competition_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — HTML-native view + competition write twin search ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — html_view, competition_pack, or operator_ack gate open",
    );
  }

  if (
    html_view.pdf_view_authorized !== false ||
    html_view.pdf_primary !== false ||
    competition_pack.live_dispatch_authorized !== false ||
    competition_pack.remote_fetched !== false ||
    competition_pack.backlog_mutated !== false ||
    competition_pack.draft_written !== false ||
    competition_pack.analysis_written !== false ||
    competition_pack.merge_executed !== false ||
    competition_pack.remote_index_queried !== false ||
    competition_pack.twin_written !== false ||
    competition_pack.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    asset_id,
    html_view,
    competition_pack,
    pack_ready,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    remote_index_queried: false,
    twin_written: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "html_native_competition_write_twin_search_compose_advisory",
  };
}

export function formatHtmlNativeCompetitionWriteTwinSearchSummary(
  c: HtmlNativeCompetitionWriteTwinSearchCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `html_ready=${c.html_view.pack_ready} · ` +
    `competition_ready=${c.competition_pack.pack_ready} · ` +
    `hits=${c.competition_pack.twin_search.search.hits.length} · ` +
    `pdf_view_authorized=false · pdf_primary=false · ` +
    `remote_index_queried=false · twin_written=false · draft_written=false`
  );
}
