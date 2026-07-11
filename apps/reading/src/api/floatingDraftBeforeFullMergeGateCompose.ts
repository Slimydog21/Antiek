/**
 * Floating draft-before-full-merge gate (pure).
 *
 * Operator vision: after floating deep research, create a draft version with
 * the combined document before fully merging into the parent asset. Full merge
 * requires a separate full_merge_ack after draft_ready.
 *
 * draft_written always false.
 * merge_executed always false.
 * live_dispatched always false.
 */

import {
  composeFloatingResearchDraftCombinedDocument,
  type FloatingDraftSource,
  type ProvisionalCombinedDraft,
} from "./floatingResearchDraftCombinedDocument";
import {
  composeFloatingInstanceTray,
  type FloatingInstanceTrayCompose,
  type TrayMember,
} from "./floatingInstanceTrayCompose";

export type MergeStage = "draft_only" | "promote_full_merge";

export interface FloatingDraftBeforeFullMergeGateInput {
  session_id: string;
  parent_asset_id: string;
  /** Optional parent document excerpt (caller-supplied). */
  parent_excerpt?: string | null;
  sources: FloatingDraftSource[];
  /**
   * draft_only — compose provisional combined draft.
   * promote_full_merge — requires draft_ready + full_merge_ack + completed sources.
   */
  stage: MergeStage;
  /** Ack for draft preview / tray draft intent. */
  operator_ack: boolean;
  /**
   * Separate ack for promoting draft → full parent merge intent.
   * Required when stage=promote_full_merge. Never executes merge.
   */
  full_merge_ack?: boolean;
}

export interface FloatingDraftBeforeFullMergeGateCompose {
  session_id: string;
  parent_asset_id: string;
  stage: MergeStage;
  draft: ProvisionalCombinedDraft;
  tray: FloatingInstanceTrayCompose | null;
  /**
   * True when draft_ready and operator_ack (draft stage),
   * or when promote path gates pass (still merge_executed=false).
   */
  gate_ready: boolean;
  /** True only when stage=promote_full_merge and all full-merge gates pass. */
  full_merge_intent_ready: boolean;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  notes: string[];
  authority: "floating_draft_before_full_merge_gate_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Gate: provisional combined draft first; optional full-merge intent after.
 * Never writes draft; never merges parent.
 */
export function composeFloatingDraftBeforeFullMergeGate(
  input: FloatingDraftBeforeFullMergeGateInput,
): FloatingDraftBeforeFullMergeGateCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (input.stage !== "draft_only" && input.stage !== "promote_full_merge") {
    throw new Error("stage must be draft_only or promote_full_merge");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (!Array.isArray(input.sources) || input.sources.length === 0) {
    throw new Error("sources must be a non-empty array");
  }

  const notes: string[] = [
    "draft_written=false — provisional combined document never persisted here",
    "merge_executed=false — parent asset never mutated here",
    "live_dispatched=false",
    "full merge requires separate full_merge_ack after draft_ready",
  ];

  const draft = composeFloatingResearchDraftCombinedDocument({
    parent_asset_id,
    parent_excerpt: input.parent_excerpt,
    sources: input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft.notes.map((n) => `[draft] ${n}`));

  // Tray mirrors selected sources as members for draft_merge_one / full_merge_one
  const members: TrayMember[] = input.sources.map((s) => ({
    instance_id: s.instance_id,
    parent_asset_id: s.parent_asset_id,
    status: s.status,
  }));

  let tray: FloatingInstanceTrayCompose | null = null;
  let full_merge_intent_ready = false;
  let gate_ready = false;

  if (input.stage === "draft_only") {
    // Prefer single-source draft_merge_one when exactly one source; else no tray action
    if (input.sources.length === 1) {
      tray = composeFloatingInstanceTray({
        parent_asset_id,
        members,
        selected_instance_ids: [input.sources[0].instance_id],
        action: "draft_merge_one",
        operator_ack: input.operator_ack,
      });
      notes.push(...tray.notes.map((n) => `[tray] ${n}`));
      gate_ready =
        draft.draft_ready === true &&
        input.operator_ack === true &&
        tray.tray_ready === true;
    } else {
      notes.push(
        "multi-source draft — tray single-merge skipped; draft compose only",
      );
      gate_ready = draft.draft_ready === true && input.operator_ack === true;
    }
    if (gate_ready) {
      notes.push(
        "gate_ready=true — draft-before-merge preview ready; still draft_written=false",
      );
    } else {
      notes.push(
        "gate_ready=false — draft not ready or operator_ack missing",
      );
    }
  } else {
    // promote_full_merge
    const full_merge_ack = input.full_merge_ack === true;
    if (typeof input.full_merge_ack !== "boolean") {
      throw new Error(
        "full_merge_ack must be an explicit boolean when stage=promote_full_merge",
      );
    }
    if (!draft.draft_ready) {
      notes.push(
        "full_merge_intent blocked — draft_ready required before promote",
      );
    }
    if (!input.operator_ack) {
      notes.push("full_merge_intent blocked — operator_ack required");
    }
    if (!full_merge_ack) {
      notes.push(
        "full_merge_intent blocked — full_merge_ack required (separate from draft ack)",
      );
    }

    const allCompleted = input.sources.every((s) => s.status === "completed");
    if (!allCompleted) {
      notes.push(
        "full_merge_intent blocked — all sources must be completed for full merge",
      );
    }

    // Tray full_merge_one only supports exactly one selected completed instance.
    // Multi-source full merge is collective analysis territory — soft-gate.
    if (input.sources.length === 1 && allCompleted) {
      tray = composeFloatingInstanceTray({
        parent_asset_id,
        members,
        selected_instance_ids: [input.sources[0].instance_id],
        action: "full_merge_one",
        operator_ack: full_merge_ack && input.operator_ack,
      });
      notes.push(...tray.notes.map((n) => `[tray] ${n}`));
      full_merge_intent_ready =
        draft.draft_ready === true &&
        input.operator_ack === true &&
        full_merge_ack === true &&
        tray.tray_ready === true;
    } else if (input.sources.length > 1) {
      notes.push(
        "multi-source full merge uses collective analysis path — tray full_merge_one skipped",
      );
      full_merge_intent_ready =
        draft.draft_ready === true &&
        input.operator_ack === true &&
        full_merge_ack === true &&
        allCompleted === true;
    } else {
      full_merge_intent_ready = false;
    }

    gate_ready = full_merge_intent_ready;
    if (full_merge_intent_ready) {
      notes.push(
        "full_merge_intent_ready=true — intent only; merge_executed=false",
      );
      notes.push(
        "gate_ready=true — promote path ready; still merge_executed=false",
      );
    } else {
      notes.push("full_merge_intent_ready=false");
      notes.push("gate_ready=false — promote gates open");
    }
  }

  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    parent_asset_id,
    stage: input.stage,
    draft,
    tray,
    gate_ready,
    full_merge_intent_ready,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    notes,
    authority: "floating_draft_before_full_merge_gate_compose_advisory",
  };
}

export function formatFloatingDraftBeforeFullMergeGateSummary(
  c: FloatingDraftBeforeFullMergeGateCompose,
): string {
  return (
    `gate_ready=${c.gate_ready} · stage=${c.stage} · ` +
    `draft_ready=${c.draft.draft_ready} · ` +
    `full_merge_intent_ready=${c.full_merge_intent_ready} · ` +
    `draft_written=false · merge_executed=false · live_dispatched=false`
  );
}
