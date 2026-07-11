/**
 * Chase → twin feed → collective analysis loop compose (pure).
 *
 * Operator vision: send subagents to chase questions while wrestling; record
 * insights/questions into twin substrate; merge completed chases into written
 * analysis — one pure end-to-end research loop without live dispatch.
 *
 * live_dispatched always false.
 * twin_written always false.
 * analysis_written always false.
 * record_persisted always false.
 * pack_dispatched always false.
 */

import {
  composeResearchInterrogationSubagentChase,
  type ChaseMode,
  type ChaseQuestion,
  type ResearchInterrogationSubagentChaseCompose,
  type SourceFamilyHint,
} from "./researchInterrogationSubagentChaseCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";
import {
  composeChaseCompletionCollectiveAnalysis,
  type ChaseCompletionCollectiveAnalysisCompose,
  type CompletedChaseSlot,
} from "./chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";

export interface ChaseTwinAnalysisLoopInput {
  session_id: string;
  parent_asset_id: string;
  questions: ChaseQuestion[];
  chase_mode: ChaseMode;
  would_exceed: boolean | null;
  operator_override?: boolean;
  selected_model_id?: string | null;
  source_families?: SourceFamilyHint[] | null;
  /**
   * Completed chase slots after chases finish (caller-supplied status/findings).
   * For pure compose, may include completed placeholders derived from plan.
   */
  completed_slots: CompletedChaseSlot[];
  /**
   * Findings for twin feed (caller-supplied). If empty, derived from
   * completed_slots findings when present.
   */
  twin_findings?: ChaseFeedFinding[] | null;
  analysis_kind: AnalysisMergeKind;
  analysis_excerpt?: string | null;
  existing_twin_asset_id?: string | null;
  operator_ack: boolean;
  mark_for_prompt_context?: boolean;
}

export interface ChaseTwinAnalysisLoopCompose {
  session_id: string;
  parent_asset_id: string;
  chase: ResearchInterrogationSubagentChaseCompose;
  twin_feed: TwinChaseAnalysisFeedCompose | null;
  analysis: ChaseCompletionCollectiveAnalysisCompose | null;
  /**
   * True when chase_ready and twin feed_ready and analysis_ready.
   * Still never dispatches, writes twin, or writes analysis.
   */
  loop_ready: boolean;
  live_dispatched: false;
  twin_written: false;
  analysis_written: false;
  record_persisted: false;
  pack_dispatched: false;
  notes: string[];
  authority: "chase_twin_analysis_loop_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose interrogation chase → twin feed → collective analysis loop.
 */
export function composeChaseTwinAnalysisLoop(
  input: ChaseTwinAnalysisLoopInput,
): ChaseTwinAnalysisLoopCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

  const notes: string[] = [
    "live_dispatched=false — loop is pure intent only",
    "twin_written=false — twin scaffold only",
    "analysis_written=false — analysis intent only",
    "record_persisted=false",
    "pack_dispatched=false",
  ];

  const chase = composeResearchInterrogationSubagentChase({
    session_id,
    parent_asset_id,
    questions: input.questions,
    chase_mode: input.chase_mode,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    selected_model_id: input.selected_model_id,
    source_families: input.source_families,
    operator_ack: input.operator_ack,
    mark_for_twin_record: true,
  });
  notes.push(...chase.notes);

  // Derive twin findings from completed slots if not provided
  let twin_findings: ChaseFeedFinding[] = [];
  if (input.twin_findings != null) {
    if (!Array.isArray(input.twin_findings)) {
      throw new Error("twin_findings must be an array when set");
    }
    twin_findings = input.twin_findings;
  } else if (Array.isArray(input.completed_slots)) {
    for (const slot of input.completed_slots) {
      if (!slot || typeof slot !== "object") continue;
      if (slot.findings != null && Array.isArray(slot.findings)) {
        for (let i = 0; i < slot.findings.length; i++) {
          const body = slot.findings[i];
          if (typeof body === "string" && body.trim()) {
            twin_findings.push({
              source_id: `${slot.slot_id}_f${i}`,
              body: body.trim(),
              kind: "insight",
            });
          }
        }
      } else if (slot.body && typeof slot.body === "string" && slot.body.trim()) {
        twin_findings.push({
          source_id: slot.slot_id,
          body: slot.body.trim(),
          kind: "question",
        });
      }
    }
  }

  let twin_feed: TwinChaseAnalysisFeedCompose | null = null;
  if (twin_findings.length > 0) {
    twin_feed = composeTwinChaseAnalysisFeed({
      session_id,
      parent_asset_id,
      findings: twin_findings,
      analysis_excerpt: input.analysis_excerpt,
      existing_twin_asset_id: input.existing_twin_asset_id,
      operator_ack: input.operator_ack,
      mark_for_prompt_context: input.mark_for_prompt_context,
    });
    notes.push(...twin_feed.notes);
  } else {
    notes.push("twin_feed skipped — no twin_findings or slot findings");
  }

  let analysis: ChaseCompletionCollectiveAnalysisCompose | null = null;
  if (
    Array.isArray(input.completed_slots) &&
    input.completed_slots.length >= 2
  ) {
    analysis = composeChaseCompletionCollectiveAnalysis({
      session_id,
      parent_asset_id,
      slots: input.completed_slots,
      kind: input.analysis_kind,
      operator_ack: input.operator_ack,
    });
    notes.push(...analysis.notes);
  } else {
    notes.push(
      "analysis skipped — need ≥2 completed_slots for collective analysis",
    );
  }

  const loop_ready =
    chase.chase_ready &&
    twin_feed != null &&
    twin_feed.feed_ready &&
    analysis != null &&
    analysis.analysis_ready;

  if (!chase.chase_ready) {
    notes.push("loop_ready=false — chase not ready");
  } else if (twin_feed == null || !twin_feed.feed_ready) {
    notes.push("loop_ready=false — twin feed not ready");
  } else if (analysis == null || !analysis.analysis_ready) {
    notes.push("loop_ready=false — analysis not ready");
  } else {
    notes.push(
      "loop_ready=true — chase→twin→analysis intent only; still pure",
    );
  }

  if (
    chase.live_dispatched !== false ||
    (twin_feed != null &&
      (twin_feed.twin_written !== false ||
        twin_feed.record_persisted !== false)) ||
    (analysis != null &&
      (analysis.analysis_written !== false ||
        analysis.live_dispatched !== false ||
        analysis.pack_dispatched !== false))
  ) {
    throw new Error("invariant: nested honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("twin_written=false");
  notes.push("analysis_written=false");
  notes.push("record_persisted=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    parent_asset_id,
    chase,
    twin_feed,
    analysis,
    loop_ready,
    live_dispatched: false,
    twin_written: false,
    analysis_written: false,
    record_persisted: false,
    pack_dispatched: false,
    notes,
    authority: "chase_twin_analysis_loop_compose_advisory",
  };
}

export function formatChaseTwinAnalysisLoopSummary(
  c: ChaseTwinAnalysisLoopCompose,
): string {
  return (
    `loop_ready=${c.loop_ready} · chase_ready=${c.chase.chase_ready} · ` +
    `feed_ready=${c.twin_feed ? c.twin_feed.feed_ready : "n/a"} · ` +
    `analysis_ready=${c.analysis ? c.analysis.analysis_ready : "n/a"} · ` +
    `live_dispatched=false · twin_written=false · analysis_written=false · ` +
    `record_persisted=false · pack_dispatched=false`
  );
}
