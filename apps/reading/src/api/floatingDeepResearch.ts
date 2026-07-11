/**
 * Floating deep research instances (pure client model).
 *
 * Operator vision: spin up a deep-research window from a reading/research
 * highlight; float it, open fullscreen, draft-merge into parent, fully merge,
 * or select multiple completed instances into a collective pack.
 *
 * Never invents live dispatch or executed merges. live_dispatched and
 * merge_executed are always false in this pure layer.
 */

export type FloatingResearchViewMode =
  | "floating"
  | "fullscreen"
  | "merged_draft"
  | "merged_full"
  | "collective";

export type FloatingResearchStatus =
  | "proposed"
  | "open"
  | "completed"
  | "closed";

export interface FloatingDeepResearchInstance {
  instance_id: string;
  parent_asset_id: string;
  highlight: string;
  prompt: string;
  view_mode: FloatingResearchViewMode;
  status: FloatingResearchStatus;
  /** Always false in pure layer — no provider dispatch. */
  live_dispatched: false;
  /** Always false in pure layer — merge is intent-only. */
  merge_executed: false;
  notes: string[];
  authority: "operator_spawn_only";
}

export interface MergeIntent {
  kind: "draft_merge" | "full_merge";
  instance_id: string;
  parent_asset_id: string;
  /** Always false — intent only, never auto-merge. */
  merge_executed: false;
  operator_ack: boolean;
  notes: string[];
}

export interface CollectivePackIntent {
  kind: "collective_pack";
  parent_asset_id: string;
  instance_ids: string[];
  /** Always false — pack proposal only. */
  pack_dispatched: false;
  notes: string[];
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function newInstanceId(parent: string, highlight: string): string {
  // Deterministic-enough client id without crypto dependency.
  const base = `${parent}:${highlight.slice(0, 48)}`;
  let h = 0;
  for (let i = 0; i < base.length; i++) {
    h = (h * 31 + base.charCodeAt(i)) | 0;
  }
  return `fdr_${Math.abs(h).toString(36)}_${parent.slice(0, 12)}`;
}

/**
 * Spawn a floating deep-research instance from a highlight.
 * Fail closed on gated highlights and empty fields.
 * live_dispatched is always false.
 */
export function spawnFloatingFromHighlight(input: {
  parent_asset_id: string;
  highlight: string;
  prompt?: string;
  gated: boolean;
  view_mode?: FloatingResearchViewMode;
}): FloatingDeepResearchInstance {
  if (typeof input.gated !== "boolean") {
    throw new Error(
      "gated must be an explicit boolean from highlight provenance (fail closed)",
    );
  }
  if (input.gated === true) {
    throw new Error("gated/withheld highlight cannot spawn floating deep research");
  }
  const parent = requireNonEmpty(input.parent_asset_id, "parent_asset_id");
  const highlight = requireNonEmpty(input.highlight, "highlight");
  const prompt =
    typeof input.prompt === "string" && input.prompt.trim()
      ? input.prompt.trim()
      : `Deep research on highlight from ${parent}`;
  const view_mode = input.view_mode ?? "floating";
  if (
    view_mode !== "floating" &&
    view_mode !== "fullscreen" &&
    view_mode !== "merged_draft" &&
    view_mode !== "merged_full" &&
    view_mode !== "collective"
  ) {
    throw new Error("view_mode invalid");
  }
  if (view_mode === "merged_full" || view_mode === "merged_draft") {
    throw new Error(
      "spawn cannot start already-merged; use proposeDraftMerge/proposeFullMerge",
    );
  }
  if (view_mode === "collective") {
    throw new Error("spawn cannot start as collective; use proposeCollectivePack");
  }

  const notes = [
    "spawned from highlight — pure client instance (no live dispatch)",
    "live_dispatched=false",
    "merge_executed=false",
  ];

  return {
    instance_id: newInstanceId(parent, highlight),
    parent_asset_id: parent,
    highlight,
    prompt,
    view_mode,
    status: "proposed",
    live_dispatched: false,
    merge_executed: false,
    notes,
    authority: "operator_spawn_only",
  };
}

export function setFloatingViewMode(
  instance: FloatingDeepResearchInstance,
  view_mode: FloatingResearchViewMode,
): FloatingDeepResearchInstance {
  if (!instance || typeof instance !== "object") {
    throw new Error("instance must be an object");
  }
  if (instance.live_dispatched !== false) {
    throw new Error("live_dispatched must be false (pure layer)");
  }
  if (instance.merge_executed !== false) {
    throw new Error("merge_executed must be false (pure layer)");
  }
  if (
    view_mode !== "floating" &&
    view_mode !== "fullscreen" &&
    view_mode !== "merged_draft" &&
    view_mode !== "merged_full" &&
    view_mode !== "collective"
  ) {
    throw new Error("view_mode invalid");
  }
  if (view_mode === "merged_draft" || view_mode === "merged_full") {
    throw new Error("use proposeDraftMerge/proposeFullMerge for merge modes");
  }
  if (view_mode === "collective") {
    throw new Error("use proposeCollectivePack for collective mode");
  }
  const notes = [...instance.notes, `view_mode → ${view_mode}`];
  return {
    ...instance,
    view_mode,
    status: instance.status === "proposed" ? "open" : instance.status,
    live_dispatched: false,
    merge_executed: false,
    notes,
  };
}

export function markFloatingCompleted(
  instance: FloatingDeepResearchInstance,
): FloatingDeepResearchInstance {
  if (instance.live_dispatched !== false) {
    throw new Error("live_dispatched must be false (pure layer)");
  }
  return {
    ...instance,
    status: "completed",
    live_dispatched: false,
    merge_executed: false,
    notes: [
      ...instance.notes,
      "marked completed by operator (no automatic provider completion)",
    ],
  };
}

/**
 * Propose draft merge into parent asset. Never executes merge.
 */
export function proposeDraftMerge(
  instance: FloatingDeepResearchInstance,
): MergeIntent {
  if (instance.live_dispatched !== false) {
    throw new Error("live_dispatched must be false");
  }
  if (
    instance.status !== "completed" &&
    instance.status !== "open" &&
    instance.status !== "proposed"
  ) {
    throw new Error("draft merge requires proposed, open, or completed instance");
  }
  return {
    kind: "draft_merge",
    instance_id: instance.instance_id,
    parent_asset_id: instance.parent_asset_id,
    merge_executed: false,
    operator_ack: false,
    notes: [
      "draft merge intent only — provisional combined document not written",
      "merge_executed=false",
    ],
  };
}

/**
 * Propose full merge. Requires explicit operator_ack; never executes.
 */
export function proposeFullMerge(
  instance: FloatingDeepResearchInstance,
  input: { operator_ack: boolean },
): MergeIntent {
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (input.operator_ack !== true) {
    throw new Error("full merge requires operator_ack=true (fail closed)");
  }
  if (instance.live_dispatched !== false) {
    throw new Error("live_dispatched must be false");
  }
  if (instance.status !== "completed") {
    throw new Error("full merge requires completed instance");
  }
  return {
    kind: "full_merge",
    instance_id: instance.instance_id,
    parent_asset_id: instance.parent_asset_id,
    merge_executed: false,
    operator_ack: true,
    notes: [
      "full merge intent only — parent asset not mutated in pure layer",
      "merge_executed=false",
    ],
  };
}

/**
 * Propose collective pack from multiple instances (same parent).
 * Never dispatches a collective research run.
 */
export function proposeCollectivePack(
  instances: FloatingDeepResearchInstance[],
): CollectivePackIntent {
  if (!Array.isArray(instances) || instances.length < 2) {
    throw new Error("collective pack requires at least 2 instances");
  }
  const parent = instances[0].parent_asset_id;
  const ids: string[] = [];
  for (const inst of instances) {
    if (!inst || typeof inst !== "object") {
      throw new Error("each instance must be an object");
    }
    if (inst.live_dispatched !== false) {
      throw new Error("live_dispatched must be false for all instances");
    }
    if (inst.parent_asset_id !== parent) {
      throw new Error("collective pack requires same parent_asset_id");
    }
    if (inst.status !== "completed" && inst.status !== "open") {
      throw new Error("collective pack requires open or completed instances");
    }
    ids.push(inst.instance_id);
  }
  // de-dupe preserving order
  const seen = new Set<string>();
  const unique = ids.filter((id) => {
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
  if (unique.length < 2) {
    throw new Error("collective pack requires at least 2 distinct instance_ids");
  }
  return {
    kind: "collective_pack",
    parent_asset_id: parent,
    instance_ids: unique,
    pack_dispatched: false,
    notes: [
      "collective pack intent only — no multi-agent dispatch",
      "pack_dispatched=false",
    ],
  };
}

export function formatFloatingSummary(
  instance: FloatingDeepResearchInstance,
): string {
  return (
    `id=${instance.instance_id} · mode=${instance.view_mode} · ` +
    `status=${instance.status} · live_dispatched=false · merge_executed=false`
  );
}
