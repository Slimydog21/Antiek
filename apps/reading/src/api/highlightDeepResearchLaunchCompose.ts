/**
 * Highlight → deep research launch package (pure).
 *
 * Operator vision: from a reading/research highlight, spin up floating deep
 * research; choose float/fullscreen; know budget impact; optionally attach
 * arxiv/substack source families — without live dispatch.
 *
 * live_dispatched always false.
 * merge_executed always false.
 */

import {
  spawnFloatingFromHighlight,
  type FloatingDeepResearchInstance,
  type FloatingResearchViewMode,
} from "./floatingDeepResearch";

export type LaunchPreferredView = "floating" | "fullscreen";

export type SourceFamilyHint =
  | "arxiv"
  | "substack"
  | "openalex"
  | "web"
  | "custom";

export interface HighlightDeepResearchLaunchInput {
  parent_asset_id: string;
  highlight: string;
  /** Explicit gated flag from highlight provenance — fail closed if true. */
  gated: boolean;
  /** Optional operator prompt override. */
  prompt?: string;
  preferred_view_mode?: LaunchPreferredView;
  /**
   * Budget would_exceed for the proposed DR prompt; null = unknown honesty.
   */
  would_exceed: boolean | null;
  /** Operator override when budget unknown or would_exceed. */
  operator_override?: boolean;
  /** Optional selected model id (operator authority). */
  selected_model_id?: string | null;
  /** Optional source families to attach for this launch. */
  source_families?: SourceFamilyHint[] | null;
  operator_ack: boolean;
}

export interface HighlightDeepResearchLaunchCompose {
  instance: FloatingDeepResearchInstance;
  preferred_view_mode: LaunchPreferredView;
  selected_model_id: string | null;
  source_families: SourceFamilyHint[];
  source_family_count: number;
  budget_ready: boolean;
  would_exceed: boolean | null;
  /**
   * True when spawn succeeded, operator_ack, budget_ready, not gated.
   * Still never live-dispatches.
   */
  launch_ready: boolean;
  /** Always false — pure layer never dispatches providers. */
  live_dispatched: false;
  /** Always false — pure layer never merges into parent. */
  merge_executed: false;
  notes: string[];
  authority: "highlight_deep_research_launch_compose_advisory";
}

const VALID_FAMILIES = new Set<SourceFamilyHint>([
  "arxiv",
  "substack",
  "openalex",
  "web",
  "custom",
]);

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose a pure deep-research launch package from a highlight.
 * Never live-dispatches; never merges.
 */
export function composeHighlightDeepResearchLaunch(
  input: HighlightDeepResearchLaunchInput,
): HighlightDeepResearchLaunchCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.gated !== "boolean") {
    throw new Error(
      "gated must be an explicit boolean from highlight provenance (fail closed)",
    );
  }
  if (
    input.would_exceed !== null &&
    input.would_exceed !== undefined &&
    typeof input.would_exceed !== "boolean"
  ) {
    throw new Error("would_exceed must be boolean or null");
  }
  const would_exceed =
    input.would_exceed === undefined ? null : input.would_exceed;

  const override =
    input.operator_override === undefined ? false : input.operator_override;
  if (typeof override !== "boolean") {
    throw new Error("operator_override must be boolean when set");
  }

  let preferred_view_mode: LaunchPreferredView = "floating";
  if (input.preferred_view_mode != null && input.preferred_view_mode !== undefined) {
    if (
      input.preferred_view_mode !== "floating" &&
      input.preferred_view_mode !== "fullscreen"
    ) {
      throw new Error("preferred_view_mode must be floating|fullscreen");
    }
    preferred_view_mode = input.preferred_view_mode;
  }

  const notes: string[] = [
    "live_dispatched=false — launch package is pure intent only",
    "merge_executed=false — parent asset not mutated",
  ];

  // Spawn pure floating instance (reuses existing fail-closed helpers).
  const instance = spawnFloatingFromHighlight({
    parent_asset_id: input.parent_asset_id,
    highlight: input.highlight,
    gated: input.gated,
    prompt: input.prompt,
    view_mode: preferred_view_mode as FloatingResearchViewMode,
  });
  notes.push(
    `spawned instance_id=${instance.instance_id} · view_mode=${instance.view_mode}`,
  );
  notes.push("live_dispatched=false on instance");

  let selected_model_id: string | null = null;
  if (
    input.selected_model_id != null &&
    input.selected_model_id !== undefined
  ) {
    selected_model_id = requireNonEmpty(
      input.selected_model_id,
      "selected_model_id",
    );
    if (
      selected_model_id.length > 128 ||
      /sk-|api[_-]?key|secret/i.test(selected_model_id)
    ) {
      throw new Error(
        "selected_model_id must be a model id, not secret material",
      );
    }
    notes.push(`selected_model_id=${selected_model_id} (operator authority)`);
  } else {
    notes.push("selected_model_id=null — operator may choose before live launch");
  }

  const source_families: SourceFamilyHint[] = [];
  if (input.source_families != null) {
    if (!Array.isArray(input.source_families)) {
      throw new Error("source_families must be an array when set");
    }
    const seen = new Set<string>();
    for (let i = 0; i < input.source_families.length; i++) {
      const f = input.source_families[i];
      if (!VALID_FAMILIES.has(f)) {
        throw new Error(
          `source_families[${i}] must be arxiv|substack|openalex|web|custom`,
        );
      }
      if (seen.has(f)) {
        throw new Error(`duplicate source_family: ${f}`);
      }
      seen.add(f);
      source_families.push(f);
    }
  }
  notes.push(`source_family_count=${source_families.length}`);

  let budget_ready = false;
  if (would_exceed === null) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override (would_exceed unknown)",
      );
    } else {
      notes.push(
        "budget_ready=false — would_exceed unknown and no operator_override",
      );
    }
  } else if (would_exceed === true) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override despite would_exceed=true",
      );
    } else {
      notes.push("budget_ready=false — would_exceed=true");
    }
  } else {
    budget_ready = true;
    notes.push("budget_ready=true — would_exceed=false");
  }

  const launch_ready =
    input.operator_ack &&
    budget_ready &&
    instance.live_dispatched === false &&
    instance.merge_executed === false;

  if (!input.operator_ack) {
    notes.push("launch_ready=false — operator_ack required");
  } else if (!budget_ready) {
    notes.push("launch_ready=false — budget gate closed");
  } else {
    notes.push(
      "launch_ready=true — pure package ready; still live_dispatched=false",
    );
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");

  return {
    instance,
    preferred_view_mode,
    selected_model_id,
    source_families,
    source_family_count: source_families.length,
    budget_ready,
    would_exceed,
    launch_ready,
    live_dispatched: false,
    merge_executed: false,
    notes,
    authority: "highlight_deep_research_launch_compose_advisory",
  };
}

export function formatHighlightDeepResearchLaunchSummary(
  c: HighlightDeepResearchLaunchCompose,
): string {
  return (
    `launch_ready=${c.launch_ready} · mode=${c.preferred_view_mode} · ` +
    `sources=${c.source_family_count} · budget_ready=${c.budget_ready} · ` +
    `live_dispatched=false · merge_executed=false`
  );
}
