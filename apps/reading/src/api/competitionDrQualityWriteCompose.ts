/**
 * Competition DR quality + source pack → write twin collective analysis (pure).
 *
 * Operator vision: highest-quality deep research informed by competition
 * decisions + arxiv/substack citations, then fold readiness into write draft +
 * collective analysis — without live dispatch or inventing competitor data.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * draft_written / analysis_written / merge_executed always false.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
} from "./writeModeTwinCollectiveAnalysisCompose";
import type { TwinWriteSlice } from "./writeModeTwinDraftMergeCompose";
import type { CompletedChaseSlot } from "./chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";

export interface CompetitionDrQualityWriteInput
  extends CompetitionDrQualitySourcePackInput {
  draft_id: string;
  parent_asset_id: string;
  analysis_kind?: AnalysisMergeKind;
  twin_slices?: TwinWriteSlice[] | null;
  chase_slots?: CompletedChaseSlot[] | null;
  base_draft_html?: string | null;
  extra_write_findings?: string[] | null;
  require_both_with_write?: boolean;
}

export interface CompetitionDrQualityWriteCompose {
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  quality_source: CompetitionDrQualitySourcePackCompose;
  write_pack: WriteModeTwinCollectiveAnalysisCompose;
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "competition_dr_quality_write_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Derive write slices/slots from competition residuals + citation titles.
 */
function deriveFromCompetition(
  parent_asset_id: string,
  quality_source: CompetitionDrQualitySourcePackCompose,
): { slices: TwinWriteSlice[]; slots: CompletedChaseSlot[] } {
  const insights: string[] = [];
  const questions: string[] = [];
  const slots: CompletedChaseSlot[] = [];

  for (const c of quality_source.citations.citations) {
    insights.push(c.title);
    slots.push({
      slot_id: `cite-${c.citation_id}`,
      question_id: c.citation_id,
      parent_asset_id,
      status: "completed",
      findings: [c.title],
      body: c.title,
    });
  }

  // Residuals from competition behind items as open questions.
  for (const row of quality_source.competition.decisions) {
    if (row.antiek_status === "behind" && row.residual) {
      questions.push(row.residual);
      slots.push({
        slot_id: `gap-${row.competitor}-${row.area}`,
        question_id: `${row.competitor}-${row.area}`,
        parent_asset_id,
        status: "open",
        findings: [row.residual],
        body: row.residual,
      });
    } else if (row.decision_summary) {
      insights.push(
        `${row.competitor}/${row.area}: ${row.decision_summary}`,
      );
    }
  }

  if (insights.length === 0 && questions.length === 0) {
    questions.push("What competition gaps remain for Antiek DR quality?");
  }

  while (slots.length < 2) {
    const i = slots.length;
    slots.push({
      slot_id: `cq-pad-${i}`,
      question_id: `pad-${i}`,
      parent_asset_id,
      status: "open",
      findings: [`padding-${i}`],
      body: `padding-${i}`,
    });
  }

  return {
    slices: [{ parent_asset_id, insights, questions }],
    slots,
  };
}

/**
 * Compose competition DR quality/source pack with write twin/analysis.
 * Never dispatches, scrapes, or writes assets.
 */
export function composeCompetitionDrQualityWrite(
  input: CompetitionDrQualityWriteInput,
): CompetitionDrQualityWriteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const draft_id = requireNonEmpty(input.draft_id, "draft_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

  const require_both_with_write =
    input.require_both_with_write === undefined
      ? true
      : input.require_both_with_write;
  if (typeof require_both_with_write !== "boolean") {
    throw new Error("require_both_with_write must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "draft_written=false · analysis_written=false · merge_executed=false",
    "store_mutated=false · live_dispatched=false",
  ];

  const quality_source = composeCompetitionDrQualitySourcePack({
    session_id: input.session_id,
    competitor_decisions: input.competitor_decisions,
    focus_areas: input.focus_areas,
    requested_families: input.requested_families,
    citations: input.citations,
    filter_to_selected_families: input.filter_to_selected_families,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    operator_ack: input.operator_ack,
    require_no_behind_gaps: input.require_no_behind_gaps,
  });
  notes.push(...quality_source.notes.map((n) => `[quality_source] ${n}`));

  let twin_slices: TwinWriteSlice[];
  let chase_slots: CompletedChaseSlot[];
  if (input.twin_slices != null && input.chase_slots != null) {
    twin_slices = input.twin_slices;
    chase_slots = input.chase_slots;
    notes.push("twin_slices/chase_slots caller-supplied");
  } else {
    const derived = deriveFromCompetition(parent_asset_id, quality_source);
    twin_slices = input.twin_slices ?? derived.slices;
    chase_slots = input.chase_slots ?? derived.slots;
    notes.push(
      `derived twin_slices=${twin_slices.length} slots=${chase_slots.length} from competition+citations`,
    );
  }

  while (chase_slots.length < 2) {
    const i = chase_slots.length;
    chase_slots = [
      ...chase_slots,
      {
        slot_id: `cq-pad-${i}`,
        question_id: `pad-${i}`,
        parent_asset_id,
        status: "open",
        findings: [`padding-${i}`],
        body: `padding-${i}`,
      },
    ];
    notes.push("chase_slots padded to ≥2 for write collective analysis");
  }

  let analysis_kind: AnalysisMergeKind =
    input.analysis_kind ?? "draft_analysis";
  const completed = chase_slots.filter((s) => s.status === "completed");
  const all_completed =
    chase_slots.length >= 2 && completed.length === chase_slots.length;
  if (
    input.analysis_kind == null &&
    all_completed &&
    input.operator_ack === true
  ) {
    analysis_kind = "full_analysis";
  }
  if (analysis_kind === "full_analysis" && !all_completed) {
    analysis_kind = "draft_analysis";
    notes.push(
      "analysis_kind demoted to draft_analysis — full needs all slots completed",
    );
  }
  if (analysis_kind === "full_analysis" && input.operator_ack !== true) {
    analysis_kind = "draft_analysis";
    notes.push(
      "analysis_kind demoted to draft_analysis — full_analysis requires operator_ack",
    );
  }

  const write_pack = composeWriteModeTwinCollectiveAnalysis({
    session_id,
    draft_id,
    parent_asset_id,
    twin_slices,
    base_draft_html: input.base_draft_html,
    chase_slots,
    analysis_kind,
    extra_findings: input.extra_write_findings,
    operator_ack: input.operator_ack,
    require_both: true,
  });
  notes.push(...write_pack.notes.map((n) => `[write_pack] ${n}`));

  let pack_ready = false;
  if (require_both_with_write) {
    pack_ready =
      quality_source.pack_ready === true &&
      write_pack.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (quality_source.pack_ready === true || write_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition quality/source + write pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — quality_source, write pack, or operator_ack gate open",
    );
  }

  if (
    quality_source.live_dispatch_authorized !== false ||
    quality_source.remote_fetched !== false ||
    quality_source.backlog_mutated !== false ||
    write_pack.draft_written !== false ||
    write_pack.analysis_written !== false ||
    write_pack.merge_executed !== false ||
    write_pack.live_dispatched !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    draft_id,
    parent_asset_id,
    quality_source,
    write_pack,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "competition_dr_quality_write_compose_advisory",
  };
}

export function formatCompetitionDrQualityWriteSummary(
  c: CompetitionDrQualityWriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `quality_ready=${c.quality_source.pack_ready} · ` +
    `write_ready=${c.write_pack.pack_ready} · ` +
    `behind=${c.quality_source.competition.behind_count} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · ` +
    `draft_written=false · analysis_written=false`
  );
}
