/**
 * Research workstation full-loop super-compose (pure).
 *
 * Operator vision: live in the research workstation — wrestle, attach
 * knowledge-dense HTML sources, float/fullscreen deep research, pick a
 * model under budget — as one coherent loop snapshot.
 *
 * live_dispatch_authorized always false.
 */

import {
  composeResearchWrestleSession,
  type ResearchWrestleSessionInput,
  type ResearchWrestleSessionSupercompose,
} from "./researchWrestleSessionSupercompose";

export interface FullLoopSourceAttachSignal {
  attach_ready: boolean;
  remote_fetched: false;
  source_count: number;
}

export interface FullLoopViewModeSignal {
  preferred_view_mode: "floating" | "fullscreen" | null;
  floating_instance_count: number;
}

export interface FullLoopBudgetSignal {
  would_exceed: boolean | null;
  selected_model_id?: string | null;
  operator_override?: boolean;
}

export interface ResearchWorkstationFullLoopInput {
  wrestle: ResearchWrestleSessionInput;
  source_attach: FullLoopSourceAttachSignal;
  view_mode: FullLoopViewModeSignal;
  budget: FullLoopBudgetSignal;
}

export interface ResearchWorkstationFullLoopSupercompose {
  wrestle: ResearchWrestleSessionSupercompose;
  source_attach_ready: boolean;
  view_mode_ready: boolean;
  budget_ready: boolean;
  /**
   * True when wrestle_ready and source attach ready and view mode ready
   * and budget ready. Still never authorizes live dispatch.
   */
  full_loop_ready: boolean;
  live_dispatch_authorized: false;
  notes: string[];
  authority: "research_workstation_full_loop_supercompose_advisory";
}

/**
 * Super-compose the full research workstation loop from pure gate signals.
 * Never live-dispatches.
 */
export function composeResearchWorkstationFullLoop(
  input: ResearchWorkstationFullLoopInput,
): ResearchWorkstationFullLoopSupercompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (!input.source_attach || typeof input.source_attach !== "object") {
    throw new Error("source_attach must be an object");
  }
  if (!input.view_mode || typeof input.view_mode !== "object") {
    throw new Error("view_mode must be an object");
  }
  if (!input.budget || typeof input.budget !== "object") {
    throw new Error("budget must be an object");
  }
  if (typeof input.source_attach.attach_ready !== "boolean") {
    throw new Error("source_attach.attach_ready must be an explicit boolean");
  }
  if (input.source_attach.remote_fetched !== false) {
    throw new Error("source_attach.remote_fetched must be false (pure layer)");
  }
  if (
    typeof input.source_attach.source_count !== "number" ||
    !Number.isInteger(input.source_attach.source_count) ||
    input.source_attach.source_count < 0
  ) {
    throw new Error("source_attach.source_count must be a non-negative integer");
  }
  if (
    typeof input.view_mode.floating_instance_count !== "number" ||
    !Number.isInteger(input.view_mode.floating_instance_count) ||
    input.view_mode.floating_instance_count < 0
  ) {
    throw new Error(
      "view_mode.floating_instance_count must be a non-negative integer",
    );
  }
  if (
    input.view_mode.preferred_view_mode != null &&
    input.view_mode.preferred_view_mode !== "floating" &&
    input.view_mode.preferred_view_mode !== "fullscreen"
  ) {
    throw new Error(
      "view_mode.preferred_view_mode must be floating|fullscreen|null",
    );
  }
  if (
    input.budget.would_exceed !== null &&
    input.budget.would_exceed !== undefined &&
    typeof input.budget.would_exceed !== "boolean"
  ) {
    throw new Error("budget.would_exceed must be boolean or null");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false — full loop is advisory readiness only",
    "remote_fetched=false on source attach signal",
  ];

  // Align wrestle input preferred_view_mode with view_mode signal when set.
  const wrestleInput: ResearchWrestleSessionInput = {
    ...input.wrestle,
    preferred_view_mode:
      input.view_mode.preferred_view_mode ??
      input.wrestle.preferred_view_mode ??
      null,
    would_exceed:
      input.budget.would_exceed === undefined
        ? input.wrestle.would_exceed
        : input.budget.would_exceed,
    operator_override:
      input.budget.operator_override === undefined
        ? input.wrestle.operator_override
        : input.budget.operator_override,
    floating_instance_count: Math.max(
      input.wrestle.floating_instance_count,
      input.view_mode.floating_instance_count,
    ),
  };

  const wrestle = composeResearchWrestleSession(wrestleInput);
  notes.push(...wrestle.notes);

  const source_attach_ready =
    input.source_attach.attach_ready &&
    input.source_attach.source_count >= 1;
  notes.push(
    source_attach_ready
      ? `source_attach_ready=true · sources=${input.source_attach.source_count}`
      : "source_attach_ready=false",
  );

  const view_mode_ready =
    input.view_mode.floating_instance_count >= 1 ||
    wrestle.floating_ready ||
    wrestle.twin_ready ||
    wrestle.questions_active;
  notes.push(
    view_mode_ready
      ? `view_mode_ready=true · preferred=${input.view_mode.preferred_view_mode ?? "null"}`
      : "view_mode_ready=false — no floating/twin/question substrate",
  );

  // Budget readiness reuses wrestle.budget_ready (already computed with override).
  const budget_ready = wrestle.budget_ready;
  notes.push(
    budget_ready
      ? "budget_ready=true"
      : "budget_ready=false — would_exceed unknown/true without override",
  );

  if (
    input.budget.selected_model_id != null &&
    input.budget.selected_model_id !== undefined
  ) {
    if (
      typeof input.budget.selected_model_id !== "string" ||
      !input.budget.selected_model_id.trim()
    ) {
      throw new Error(
        "budget.selected_model_id must be non-empty string when set",
      );
    }
    notes.push(
      `selected_model_id=${input.budget.selected_model_id.trim()} (operator authority)`,
    );
  }

  const full_loop_ready =
    wrestle.wrestle_ready &&
    source_attach_ready &&
    view_mode_ready &&
    budget_ready;

  notes.push(
    full_loop_ready
      ? "full_loop_ready=true — wrestle+sources+view+budget pass"
      : "full_loop_ready=false — continue closing gates",
  );
  notes.push("live_dispatch_authorized=false");

  return {
    wrestle,
    source_attach_ready,
    view_mode_ready,
    budget_ready,
    full_loop_ready,
    live_dispatch_authorized: false,
    notes,
    authority: "research_workstation_full_loop_supercompose_advisory",
  };
}

export function formatResearchWorkstationFullLoopSummary(
  c: ResearchWorkstationFullLoopSupercompose,
): string {
  return (
    `full_loop_ready=${c.full_loop_ready} · wrestle=${c.wrestle.wrestle_ready} · ` +
    `sources=${c.source_attach_ready} · view=${c.view_mode_ready} · ` +
    `budget=${c.budget_ready} · live_dispatch_authorized=false`
  );
}
