/**
 * Write-mode twin draft + collective analysis pack (pure).
 *
 * Operator vision: after subagent chases complete, merge findings into written
 * analysis; also fold twin note-taker substrate into a provisional write draft
 * before full author commit — HTML-native writing surface.
 *
 * draft_written always false.
 * analysis_written always false.
 * merge_executed always false.
 * store_mutated always false.
 * live_dispatched always false.
 */

import {
  composeWriteModeTwinDraftMerge,
  type TwinWriteSlice,
  type WriteModeTwinDraftMergeCompose,
} from "./writeModeTwinDraftMergeCompose";
import {
  composeChaseCompletionCollectiveAnalysis,
  type ChaseCompletionCollectiveAnalysisCompose,
  type CompletedChaseSlot,
} from "./chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";

export interface WriteModeTwinCollectiveAnalysisInput {
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  /** Twin slices for write draft (caller-supplied). */
  twin_slices: TwinWriteSlice[];
  base_draft_html?: string | null;
  /** Completed chase slots for collective analysis. */
  chase_slots: CompletedChaseSlot[];
  analysis_kind: AnalysisMergeKind;
  extra_findings?: string[] | null;
  operator_ack: boolean;
  /**
   * When true (default), require both draft_ready and analysis_ready for pack.
   * When false, pack_ready if either path ready.
   */
  require_both?: boolean;
}

export interface WriteModeTwinCollectiveAnalysisCompose {
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  twin_draft: WriteModeTwinDraftMergeCompose;
  collective_analysis: ChaseCompletionCollectiveAnalysisCompose;
  /**
   * True when twin_draft.draft_ready and collective_analysis.analysis_ready
   * (or either when require_both=false) and operator_ack.
   */
  pack_ready: boolean;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "write_mode_twin_collective_analysis_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose twin→write draft + chase-completion collective analysis.
 * Never writes draft/analysis assets; never merges published write.
 */
export function composeWriteModeTwinCollectiveAnalysis(
  input: WriteModeTwinCollectiveAnalysisInput,
): WriteModeTwinCollectiveAnalysisCompose {
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

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false — provisional write draft not persisted",
    "analysis_written=false — collective analysis intent only",
    "merge_executed=false — published write not mutated",
    "store_mutated=false · live_dispatched=false",
  ];

  const twin_draft = composeWriteModeTwinDraftMerge({
    draft_id,
    base_draft_html: input.base_draft_html,
    slices: input.twin_slices,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin_draft.notes.map((n) => `[twin_draft] ${n}`));

  // Ensure all chase slots share parent_asset_id
  const slots = input.chase_slots;
  if (!Array.isArray(slots) || slots.length < 2) {
    throw new Error("chase_slots must be an array with at least 2 slots");
  }
  for (let i = 0; i < slots.length; i++) {
    const s = slots[i];
    if (!s || typeof s !== "object") {
      throw new Error(`chase_slots[${i}] must be an object`);
    }
    if (s.parent_asset_id.trim() !== parent_asset_id) {
      throw new Error(
        "all chase_slots must share input.parent_asset_id",
      );
    }
  }

  const collective_analysis = composeChaseCompletionCollectiveAnalysis({
    session_id,
    parent_asset_id,
    slots,
    kind: input.analysis_kind,
    operator_ack: input.operator_ack,
    extra_findings: input.extra_findings,
  });
  notes.push(
    ...collective_analysis.notes.map((n) => `[collective] ${n}`),
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      twin_draft.draft_ready === true &&
      collective_analysis.analysis_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (twin_draft.draft_ready === true ||
        collective_analysis.analysis_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin write draft + collective analysis intent ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — twin draft, collective analysis, or operator_ack gate open",
    );
  }

  if (
    twin_draft.draft_written !== false ||
    twin_draft.merge_executed !== false ||
    twin_draft.store_mutated !== false ||
    collective_analysis.analysis_written !== false ||
    collective_analysis.live_dispatched !== false ||
    collective_analysis.pack_dispatched !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    draft_id,
    parent_asset_id,
    twin_draft,
    collective_analysis,
    pack_ready,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "write_mode_twin_collective_analysis_compose_advisory",
  };
}

export function formatWriteModeTwinCollectiveAnalysisSummary(
  c: WriteModeTwinCollectiveAnalysisCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · draft_ready=${c.twin_draft.draft_ready} · ` +
    `analysis_ready=${c.collective_analysis.analysis_ready} · ` +
    `kind=${c.collective_analysis.analysis.kind} · ` +
    `draft_written=false · analysis_written=false · merge_executed=false`
  );
}
