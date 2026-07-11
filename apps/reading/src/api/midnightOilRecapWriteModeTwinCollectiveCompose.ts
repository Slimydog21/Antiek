/**
 * Midnight Oil unattended recap → write-mode twin collective analysis (pure).
 *
 * Operator vision: after unattended MO completes, review recap then fold
 * progress into write draft + collective analysis without live write/dispatch.
 *
 * live_execution_authorized / draft_written / analysis_written /
 * merge_executed / store_mutated always false.
 */

import {
  composeMidnightOilUnattendedRecap,
  type MidnightOilUnattendedRecapCompose,
  type MidnightOilRecapGoal,
} from "./midnightOilUnattendedRecapCompose";
import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
} from "./writeModeTwinCollectiveAnalysisCompose";
import type { TwinWriteSlice } from "./writeModeTwinDraftMergeCompose";
import type { CompletedChaseSlot } from "./chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";

export type { MidnightOilRecapGoal };

export interface MidnightOilRecapWriteModeTwinCollectiveInput {
  run_id: string;
  operator_id: string;
  work_minutes_planned: number;
  work_minutes_actual: number | null;
  goals: MidnightOilRecapGoal[];
  price_ceiling_usd: number | null;
  spend_usd: number | null;
  artifact_ids?: string[] | null;
  operator_ack: boolean;
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  analysis_kind?: AnalysisMergeKind;
  twin_slices?: TwinWriteSlice[] | null;
  chase_slots?: CompletedChaseSlot[] | null;
  base_draft_html?: string | null;
  extra_findings?: string[] | null;
  require_both?: boolean;
}

export interface MidnightOilRecapWriteModeTwinCollectiveCompose {
  run_id: string;
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  recap: MidnightOilUnattendedRecapCompose;
  write_pack: WriteModeTwinCollectiveAnalysisCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  store_mutated: false;
  notes: string[];
  authority: "midnight_oil_recap_write_mode_twin_collective_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveSlicesAndSlots(
  parent_asset_id: string,
  goals: MidnightOilRecapGoal[],
): { slices: TwinWriteSlice[]; slots: CompletedChaseSlot[] } {
  const insights: string[] = [];
  const questions: string[] = [];
  const slots: CompletedChaseSlot[] = [];
  for (const g of goals) {
    const body = g.notes?.trim() ? `${g.title}: ${g.notes}` : g.title;
    if (g.status === "done") {
      insights.push(body);
      slots.push({
        slot_id: `mo-${g.goal_id}`,
        question_id: g.goal_id,
        parent_asset_id,
        status: "completed",
        findings: [body],
        body,
      });
    } else if (g.status === "blocked") {
      questions.push(body);
      slots.push({
        slot_id: `mo-${g.goal_id}`,
        question_id: g.goal_id,
        parent_asset_id,
        status: "closed",
        findings: [body],
        body,
      });
    } else {
      questions.push(body);
      slots.push({
        slot_id: `mo-${g.goal_id}`,
        question_id: g.goal_id,
        parent_asset_id,
        status: "open",
        findings: [body],
        body,
      });
    }
  }
  if (insights.length === 0 && questions.length === 0 && goals.length > 0) {
    for (const g of goals) {
      questions.push(g.title);
    }
  }
  const slices: TwinWriteSlice[] = [
    { parent_asset_id, insights, questions },
  ];
  return { slices, slots };
}

export function composeMidnightOilRecapWriteModeTwinCollective(
  input: MidnightOilRecapWriteModeTwinCollectiveInput,
): MidnightOilRecapWriteModeTwinCollectiveCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const run_id = requireNonEmpty(input.run_id, "run_id");
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
    "live_execution_authorized=false — recap never re-launches MO",
    "draft_written=false · analysis_written=false · merge_executed=false",
    "store_mutated=false",
  ];

  const recap = composeMidnightOilUnattendedRecap({
    run_id,
    operator_id: input.operator_id,
    work_minutes_planned: input.work_minutes_planned,
    work_minutes_actual: input.work_minutes_actual,
    goals: input.goals,
    price_ceiling_usd: input.price_ceiling_usd,
    spend_usd: input.spend_usd,
    artifact_ids: input.artifact_ids,
    operator_ack: input.operator_ack,
  });
  notes.push(...recap.notes.map((n) => `[recap] ${n}`));

  let twin_slices: TwinWriteSlice[];
  let chase_slots: CompletedChaseSlot[];
  if (input.twin_slices != null && input.chase_slots != null) {
    twin_slices = input.twin_slices;
    chase_slots = input.chase_slots;
    notes.push("twin_slices/chase_slots caller-supplied");
  } else {
    const derived = deriveSlicesAndSlots(parent_asset_id, input.goals);
    twin_slices = input.twin_slices ?? derived.slices;
    chase_slots = input.chase_slots ?? derived.slots;
    notes.push(
      `derived twin_slices=${twin_slices.length} slots=${chase_slots.length} from MO goals`,
    );
  }

  // Ensure ≥2 chase slots for write-mode collective analysis contract.
  if (chase_slots.length < 2) {
    while (chase_slots.length < 2) {
      const i = chase_slots.length;
      chase_slots = [
        ...chase_slots,
        {
          slot_id: `mo-pad-${i}`,
          question_id: `pad-${i}`,
          parent_asset_id,
          status: "open",
          findings: [`padding-slot-${i}`],
          body: `padding-slot-${i}`,
        },
      ];
    }
    notes.push("chase_slots padded to ≥2 for write collective analysis contract");
  }

  // Ensure twin slice has ≥1 insight or question for draft_ready.
  if (twin_slices.length > 0) {
    const s0 = twin_slices[0];
    if (s0.insights.length === 0 && s0.questions.length === 0) {
      twin_slices = [
        {
          ...s0,
          questions: [`Open: ${parent_asset_id}`],
        },
        ...twin_slices.slice(1),
      ];
      notes.push("twin_slices padded with placeholder question");
    }
  }

  let analysis_kind: AnalysisMergeKind =
    input.analysis_kind ?? "draft_analysis";
  const completed = chase_slots.filter((s) => s.status === "completed");
  const all_completed =
    chase_slots.length >= 2 && completed.length === chase_slots.length;
  // full_analysis requires every slot completed + operator_ack.
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
      "analysis_kind demoted to draft_analysis — full_analysis needs all slots completed",
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
    extra_findings: input.extra_findings,
    operator_ack: input.operator_ack,
    require_both: true,
  });
  notes.push(...write_pack.notes.map((n) => `[write_pack] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      recap.recap_ready === true &&
      write_pack.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (recap.recap_ready === true || write_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO recap + write twin/analysis ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — recap, write pack, or operator_ack gate open",
    );
  }

  if (
    recap.live_execution_authorized !== false ||
    recap.store_mutated !== false ||
    write_pack.draft_written !== false ||
    write_pack.analysis_written !== false ||
    write_pack.merge_executed !== false ||
    write_pack.live_dispatched !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("store_mutated=false");

  return {
    run_id,
    session_id,
    draft_id,
    parent_asset_id,
    recap,
    write_pack,
    pack_ready,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    store_mutated: false,
    notes,
    authority: "midnight_oil_recap_write_mode_twin_collective_compose_advisory",
  };
}

export function formatMidnightOilRecapWriteModeTwinCollectiveSummary(
  c: MidnightOilRecapWriteModeTwinCollectiveCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `recap_ready=${c.recap.recap_ready} · ` +
    `write_ready=${c.write_pack.pack_ready} · ` +
    `done=${c.recap.goals_done}/${c.recap.goal_count} · ` +
    `live_execution_authorized=false · draft_written=false · analysis_written=false`
  );
}
