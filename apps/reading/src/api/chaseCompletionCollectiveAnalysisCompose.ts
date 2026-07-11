/**
 * Chase completion → collective analysis compose (pure).
 *
 * Operator vision: after subagent deep-research chases complete, merge their
 * findings into a written analysis (draft or full) without live write.
 *
 * analysis_written always false.
 * live_dispatched always false.
 * pack_dispatched always false.
 */

import {
  proposeCollectiveAnalysisMerge,
  type AnalysisMergeKind,
  type CollectiveAnalysisIntent,
  type CompletedResearchInstance,
} from "./collectiveDeepResearchMerge";

export type ChaseSlotStatus = "proposed" | "open" | "completed" | "closed";

export interface CompletedChaseSlot {
  slot_id: string;
  question_id: string;
  parent_asset_id: string;
  status: ChaseSlotStatus;
  /** Operator/caller-supplied findings — never invented. */
  findings?: string[] | null;
  body?: string;
}

export interface ChaseCompletionCollectiveAnalysisInput {
  session_id: string;
  parent_asset_id: string;
  slots: CompletedChaseSlot[];
  kind: AnalysisMergeKind;
  operator_ack: boolean;
  extra_findings?: string[] | null;
}

export interface ChaseCompletionCollectiveAnalysisCompose {
  session_id: string;
  parent_asset_id: string;
  completed_slot_count: number;
  selected_slot_ids: string[];
  analysis: CollectiveAnalysisIntent;
  /**
   * True when ≥2 completed (for full) or ≥2 non-closed (for draft) slots
   * and analysis intent composed. Never writes analysis asset.
   */
  analysis_ready: boolean;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  notes: string[];
  authority: "chase_completion_collective_analysis_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose pure collective analysis intent from completed chase slots.
 * Never writes analysis; never dispatches.
 */
export function composeChaseCompletionCollectiveAnalysis(
  input: ChaseCompletionCollectiveAnalysisInput,
): ChaseCompletionCollectiveAnalysisCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (input.kind !== "draft_analysis" && input.kind !== "full_analysis") {
    throw new Error("kind must be draft_analysis or full_analysis");
  }

  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (!Array.isArray(input.slots) || input.slots.length < 2) {
    throw new Error("slots must be an array with at least 2 chase slots");
  }

  const notes: string[] = [
    "analysis_written=false — pure collective analysis intent only",
    "live_dispatched=false — no chase re-dispatch",
    "pack_dispatched=false — no pack execution",
  ];

  const instances: CompletedResearchInstance[] = [];
  const selected_slot_ids: string[] = [];
  let completed_slot_count = 0;
  const seenSlot = new Set<string>();

  for (let i = 0; i < input.slots.length; i++) {
    const s = input.slots[i];
    if (!s || typeof s !== "object") {
      throw new Error(`slots[${i}] must be an object`);
    }
    const slot_id = requireNonEmpty(s.slot_id, `slots[${i}].slot_id`);
    if (seenSlot.has(slot_id)) {
      throw new Error(`duplicate slot_id: ${slot_id}`);
    }
    seenSlot.add(slot_id);
    requireNonEmpty(s.question_id, `slots[${i}].question_id`);
    const p = requireNonEmpty(
      s.parent_asset_id,
      `slots[${i}].parent_asset_id`,
    );
    if (p !== parent_asset_id) {
      throw new Error("all slots must share parent_asset_id");
    }
    if (
      s.status !== "proposed" &&
      s.status !== "open" &&
      s.status !== "completed" &&
      s.status !== "closed"
    ) {
      throw new Error(`slots[${i}].status invalid`);
    }
    if (s.status === "closed") {
      notes.push(`skipped closed slot ${slot_id}`);
      continue;
    }
    if (s.status === "completed") {
      completed_slot_count += 1;
    }

    const findings: string[] | undefined = [];
    if (s.findings != null) {
      if (!Array.isArray(s.findings)) {
        throw new Error(`slots[${i}].findings must be string[] when set`);
      }
      for (let j = 0; j < s.findings.length; j++) {
        const f = s.findings[j];
        if (typeof f !== "string" || !f.trim()) {
          throw new Error(
            `slots[${i}].findings[${j}] must be non-empty string`,
          );
        }
        findings.push(f.trim());
      }
    }

    selected_slot_ids.push(slot_id);
    instances.push({
      instance_id: slot_id,
      parent_asset_id: p,
      status: s.status,
      highlight: s.body,
      findings: findings.length > 0 ? findings : undefined,
    });
  }

  if (instances.length < 2) {
    throw new Error(
      "need ≥2 non-closed chase slots for collective analysis",
    );
  }

  notes.push(
    `selected_slots=${selected_slot_ids.length} · completed=${completed_slot_count}`,
  );

  let analysis: CollectiveAnalysisIntent;
  try {
    analysis = proposeCollectiveAnalysisMerge(instances, {
      kind: input.kind,
      operator_ack: input.operator_ack,
      extra_findings: input.extra_findings,
    });
  } catch (e) {
    throw e instanceof Error ? e : new Error(String(e));
  }
  notes.push(...analysis.notes);

  // analysis_ready: compose succeeded AND for full, all selected completed
  let analysis_ready = false;
  if (input.kind === "full_analysis") {
    analysis_ready =
      input.operator_ack &&
      completed_slot_count === instances.length &&
      analysis.analysis_written === false;
    if (!input.operator_ack) {
      notes.push("analysis_ready=false — full_analysis requires operator_ack");
    } else if (completed_slot_count !== instances.length) {
      notes.push(
        "analysis_ready=false — full_analysis requires all selected slots completed",
      );
    } else {
      notes.push(
        "analysis_ready=true — full analysis intent ready; analysis_written=false",
      );
    }
  } else {
    // draft: ack optional for scaffold but we mirror merge readiness
    analysis_ready = instances.length >= 2 && analysis.analysis_written === false;
    notes.push(
      analysis_ready
        ? "analysis_ready=true — draft analysis intent ready; analysis_written=false"
        : "analysis_ready=false",
    );
  }

  if (analysis.analysis_written !== false) {
    throw new Error("invariant: analysis_written must remain false");
  }

  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    parent_asset_id,
    completed_slot_count,
    selected_slot_ids,
    analysis,
    analysis_ready,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    notes,
    authority: "chase_completion_collective_analysis_compose_advisory",
  };
}

export function formatChaseCompletionCollectiveAnalysisSummary(
  c: ChaseCompletionCollectiveAnalysisCompose,
): string {
  return (
    `analysis_ready=${c.analysis_ready} · kind=${c.analysis.kind} · ` +
    `slots=${c.selected_slot_ids.length} · completed=${c.completed_slot_count} · ` +
    `analysis_written=false · live_dispatched=false · pack_dispatched=false`
  );
}
