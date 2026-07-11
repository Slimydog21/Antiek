/**
 * Floating research view-mode compose (pure).
 *
 * Operator vision: from a floating deep-research instance, choose float,
 * fullscreen, draft-merge intent, or full-merge intent — without live
 * dispatch or executed merges.
 *
 * Composes existing floatingDeepResearch helpers into one advisory snapshot.
 * live_dispatched and merge_executed are always false.
 */

import {
  proposeDraftMerge,
  proposeFullMerge,
  setFloatingViewMode,
  type FloatingDeepResearchInstance,
  type FloatingResearchViewMode,
  type MergeIntent,
} from "./floatingDeepResearch";

export type FloatingViewModeAction =
  | "float"
  | "fullscreen"
  | "propose_draft_merge"
  | "propose_full_merge";

export interface FloatingResearchViewModeComposeInput {
  instance: FloatingDeepResearchInstance;
  action: FloatingViewModeAction;
  /**
   * Required true for propose_full_merge (fail closed).
   * Ignored for float/fullscreen/draft (draft is preview intent).
   */
  operator_ack?: boolean;
}

export interface FloatingViewModeCapabilities {
  can_float: boolean;
  can_fullscreen: boolean;
  can_draft_merge: boolean;
  can_full_merge: boolean;
  current_view_mode: FloatingResearchViewMode;
  status: FloatingDeepResearchInstance["status"];
  notes: string[];
}

export interface FloatingResearchViewModeCompose {
  instance: FloatingDeepResearchInstance;
  action: FloatingViewModeAction;
  view_mode: FloatingResearchViewMode;
  merge_intent: MergeIntent | null;
  capabilities: FloatingViewModeCapabilities;
  /** True when action produced a valid next state / intent. */
  action_applied: boolean;
  /** Always false — pure layer never dispatches providers. */
  live_dispatched: false;
  /** Always false — pure layer never mutates parent assets. */
  merge_executed: false;
  notes: string[];
  authority: "floating_research_view_mode_compose_advisory";
}

function requireInstance(
  instance: unknown,
): FloatingDeepResearchInstance {
  if (!instance || typeof instance !== "object") {
    throw new Error("instance must be an object");
  }
  const inst = instance as FloatingDeepResearchInstance;
  if (inst.live_dispatched !== false) {
    throw new Error("live_dispatched must be false (pure layer)");
  }
  if (inst.merge_executed !== false) {
    throw new Error("merge_executed must be false (pure layer)");
  }
  if (typeof inst.instance_id !== "string" || !inst.instance_id.trim()) {
    throw new Error("instance.instance_id must be a non-empty string");
  }
  if (
    typeof inst.parent_asset_id !== "string" ||
    !inst.parent_asset_id.trim()
  ) {
    throw new Error("instance.parent_asset_id must be a non-empty string");
  }
  return inst;
}

/**
 * Assess what view-mode actions are valid for this pure instance.
 * Never dispatches or merges.
 */
export function assessFloatingViewModeCapabilities(
  instance: FloatingDeepResearchInstance,
): FloatingViewModeCapabilities {
  const inst = requireInstance(instance);
  const notes: string[] = [
    "capabilities are pure advisory — no live dispatch",
    "live_dispatched=false",
    "merge_executed=false",
  ];

  const closed = inst.status === "closed";
  // Float / fullscreen always available when not closed and honesty flags hold.
  const can_float = !closed;
  const can_fullscreen = !closed;
  // Draft merge intent allowed for proposed|open|completed (mirrors proposeDraftMerge).
  const can_draft_merge =
    !closed &&
    (inst.status === "proposed" ||
      inst.status === "open" ||
      inst.status === "completed");
  // Full merge only when completed (operator_ack still required at compose time).
  const can_full_merge = !closed && inst.status === "completed";

  if (closed) {
    notes.push("status=closed — no view-mode actions");
  } else {
    notes.push(
      `can_float=${can_float} can_fullscreen=${can_fullscreen} ` +
        `can_draft_merge=${can_draft_merge} can_full_merge=${can_full_merge}`,
    );
  }

  return {
    can_float,
    can_fullscreen,
    can_draft_merge,
    can_full_merge,
    current_view_mode: inst.view_mode,
    status: inst.status,
    notes,
  };
}

/**
 * Apply a pure view-mode action (float / fullscreen / draft|full merge intent).
 * Never live-dispatches; never executes merges.
 */
export function composeFloatingResearchViewMode(
  input: FloatingResearchViewModeComposeInput,
): FloatingResearchViewModeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const inst0 = requireInstance(input.instance);
  const action = input.action;
  if (
    action !== "float" &&
    action !== "fullscreen" &&
    action !== "propose_draft_merge" &&
    action !== "propose_full_merge"
  ) {
    throw new Error(
      "action must be float|fullscreen|propose_draft_merge|propose_full_merge",
    );
  }

  const capabilities = assessFloatingViewModeCapabilities(inst0);
  const notes: string[] = [
    "live_dispatched=false — no provider dispatch from view-mode compose",
    "merge_executed=false — parent asset never mutated in pure layer",
    ...capabilities.notes,
  ];

  let instance = inst0;
  let merge_intent: MergeIntent | null = null;
  let action_applied = false;

  if (action === "float") {
    if (!capabilities.can_float) {
      throw new Error("cannot float: instance closed or invalid");
    }
    instance = setFloatingViewMode(inst0, "floating");
    action_applied = true;
    notes.push("action=float → view_mode=floating");
  } else if (action === "fullscreen") {
    if (!capabilities.can_fullscreen) {
      throw new Error("cannot fullscreen: instance closed or invalid");
    }
    instance = setFloatingViewMode(inst0, "fullscreen");
    action_applied = true;
    notes.push("action=fullscreen → view_mode=fullscreen");
  } else if (action === "propose_draft_merge") {
    if (!capabilities.can_draft_merge) {
      throw new Error(
        "cannot propose draft merge: requires proposed|open|completed",
      );
    }
    merge_intent = proposeDraftMerge(inst0);
    // View mode stays non-merged; merge modes only via intent helpers.
    action_applied = true;
    notes.push(
      "action=propose_draft_merge · merge_intent kind=draft_merge · merge_executed=false",
    );
  } else {
    // propose_full_merge
    if (!capabilities.can_full_merge) {
      throw new Error("cannot propose full merge: requires completed status");
    }
    if (typeof input.operator_ack !== "boolean") {
      throw new Error(
        "operator_ack must be an explicit boolean for propose_full_merge",
      );
    }
    merge_intent = proposeFullMerge(inst0, {
      operator_ack: input.operator_ack,
    });
    action_applied = true;
    notes.push(
      "action=propose_full_merge · merge_intent kind=full_merge · merge_executed=false",
    );
  }

  // Re-assert honesty flags after helper chain.
  if (instance.live_dispatched !== false) {
    throw new Error("invariant: live_dispatched must remain false");
  }
  if (instance.merge_executed !== false) {
    throw new Error("invariant: merge_executed must remain false");
  }
  if (merge_intent != null && merge_intent.merge_executed !== false) {
    throw new Error("invariant: merge_intent.merge_executed must be false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");

  return {
    instance,
    action,
    view_mode: instance.view_mode,
    merge_intent,
    capabilities,
    action_applied,
    live_dispatched: false,
    merge_executed: false,
    notes,
    authority: "floating_research_view_mode_compose_advisory",
  };
}

export function formatFloatingViewModeComposeSummary(
  c: FloatingResearchViewModeCompose,
): string {
  const intent = c.merge_intent ? c.merge_intent.kind : "none";
  return (
    `action=${c.action} · view_mode=${c.view_mode} · intent=${intent} · ` +
    `applied=${c.action_applied} · live_dispatched=false · merge_executed=false`
  );
}
