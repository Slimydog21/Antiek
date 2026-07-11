/**
 * Reading highlight → float DR → tray merge pack compose (pure).
 *
 * Operator vision: from a reading highlight, spin floating deep research;
 * select among floating instances for fullscreen or draft/full merge into
 * the reading asset — one pure end-to-end pack without live dispatch.
 *
 * live_dispatched always false.
 * merge_executed always false.
 * pack_dispatched always false.
 */

import {
  composeHighlightDeepResearchLaunch,
  type HighlightDeepResearchLaunchCompose,
  type HighlightDeepResearchLaunchInput,
  type LaunchPreferredView,
  type SourceFamilyHint,
} from "./highlightDeepResearchLaunchCompose";
import {
  composeFloatingInstanceTray,
  type FloatingInstanceTrayCompose,
  type TrayAction,
  type TrayMember,
} from "./floatingInstanceTrayCompose";

export type ReadingSurfaceAction =
  | "spawn_only"
  | "spawn_and_fullscreen"
  | "spawn_and_draft_merge"
  | "spawn_and_full_merge"
  | "tray_collective"
  | "tray_cohesive";

export interface ReadingHighlightFloatMergeTrayInput {
  parent_asset_id: string;
  highlight: string;
  gated: boolean;
  prompt?: string;
  preferred_view_mode?: LaunchPreferredView;
  would_exceed: boolean | null;
  operator_override?: boolean;
  selected_model_id?: string | null;
  source_families?: SourceFamilyHint[] | null;
  /**
   * Existing floating instances already on the reading surface (same parent).
   * Spawned instance is appended when spawn succeeds.
   */
  existing_members?: TrayMember[] | null;
  /**
   * Selected instance ids for tray actions (may include spawned id after spawn).
   * For spawn_and_* single actions, defaults to spawned instance only.
   */
  selected_instance_ids?: string[] | null;
  surface_action: ReadingSurfaceAction;
  operator_ack: boolean;
}

export interface ReadingHighlightFloatMergeTrayCompose {
  launch: HighlightDeepResearchLaunchCompose;
  tray: FloatingInstanceTrayCompose | null;
  surface_action: ReadingSurfaceAction;
  /**
   * True when launch_ready and (spawn_only or tray_ready for tray actions).
   * Still never dispatches or merges.
   */
  surface_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  notes: string[];
  authority: "reading_highlight_float_merge_tray_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function surfaceToTrayAction(
  surface: ReadingSurfaceAction,
): TrayAction | null {
  switch (surface) {
    case "spawn_only":
      return null;
    case "spawn_and_fullscreen":
      return "fullscreen_one";
    case "spawn_and_draft_merge":
      return "draft_merge_one";
    case "spawn_and_full_merge":
      return "full_merge_one";
    case "tray_collective":
      return "collective_pack";
    case "tray_cohesive":
      return "cohesive_prompt";
    default:
      throw new Error("surface_action invalid");
  }
}

/**
 * Compose reading-surface highlight→float→tray/merge pack.
 * Never live-dispatches; never merges into parent.
 */
export function composeReadingHighlightFloatMergeTray(
  input: ReadingHighlightFloatMergeTrayInput,
): ReadingHighlightFloatMergeTrayCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const surface_action = input.surface_action;
  if (
    surface_action !== "spawn_only" &&
    surface_action !== "spawn_and_fullscreen" &&
    surface_action !== "spawn_and_draft_merge" &&
    surface_action !== "spawn_and_full_merge" &&
    surface_action !== "tray_collective" &&
    surface_action !== "tray_cohesive"
  ) {
    throw new Error("surface_action invalid");
  }

  const notes: string[] = [
    "live_dispatched=false — reading surface pack is pure intent only",
    "merge_executed=false — parent reading asset not mutated",
    "pack_dispatched=false — collective/cohesive never dispatch from pure layer",
  ];

  const launchInput: HighlightDeepResearchLaunchInput = {
    parent_asset_id: input.parent_asset_id,
    highlight: input.highlight,
    gated: input.gated,
    prompt: input.prompt,
    preferred_view_mode: input.preferred_view_mode,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    selected_model_id: input.selected_model_id,
    source_families: input.source_families,
    // For tray multi actions we still spawn first; ack applies to whole pack.
    operator_ack: input.operator_ack,
  };
  const launch = composeHighlightDeepResearchLaunch(launchInput);
  notes.push(...launch.notes);

  // Build member list: existing + spawned
  const existing: TrayMember[] = [];
  if (input.existing_members != null) {
    if (!Array.isArray(input.existing_members)) {
      throw new Error("existing_members must be an array when set");
    }
    for (let i = 0; i < input.existing_members.length; i++) {
      existing.push(input.existing_members[i]);
    }
  }
  const spawnedMember: TrayMember = {
    instance_id: launch.instance.instance_id,
    parent_asset_id: launch.instance.parent_asset_id,
    status: launch.instance.status,
    view_mode: launch.instance.view_mode,
    highlight: launch.instance.highlight,
    live_dispatched: false,
    merge_executed: false,
  };
  // Avoid duplicate if existing already has same id
  const members: TrayMember[] = existing.filter(
    (m) => m.instance_id !== spawnedMember.instance_id,
  );
  members.push(spawnedMember);

  const trayAction = surfaceToTrayAction(surface_action);
  let tray: FloatingInstanceTrayCompose | null = null;
  let surface_ready = false;

  if (trayAction === null) {
    // spawn_only
    surface_ready = launch.launch_ready;
    notes.push(
      surface_ready
        ? "surface_action=spawn_only · surface_ready=launch_ready"
        : "surface_action=spawn_only · surface_ready=false (launch not ready)",
    );
  } else {
    let selected: string[];
    if (
      surface_action === "spawn_and_fullscreen" ||
      surface_action === "spawn_and_draft_merge" ||
      surface_action === "spawn_and_full_merge"
    ) {
      selected = [launch.instance.instance_id];
    } else {
      // tray multi: require caller selection including others; ensure ≥1
      if (
        input.selected_instance_ids == null ||
        !Array.isArray(input.selected_instance_ids)
      ) {
        throw new Error(
          "selected_instance_ids required for tray_collective|tray_cohesive",
        );
      }
      selected = input.selected_instance_ids.map((id, i) =>
        requireNonEmpty(id, `selected_instance_ids[${i}]`),
      );
      // Always include spawned instance for multi-surface continuity
      if (!selected.includes(launch.instance.instance_id)) {
        selected = [...selected, launch.instance.instance_id];
        notes.push(
          "appended spawned instance_id to selection for tray multi action",
        );
      }
    }

    // For full_merge_one tray requires completed — spawn is proposed/open.
    // Fail closed honestly unless caller marks via existing completed members
    // only for multi; for spawn_and_full_merge, require status completed.
    tray = composeFloatingInstanceTray({
      parent_asset_id: requireNonEmpty(
        input.parent_asset_id,
        "parent_asset_id",
      ),
      members,
      selected_instance_ids: selected,
      action: trayAction,
      operator_ack: input.operator_ack,
    });
    notes.push(...tray.notes);

    surface_ready = launch.launch_ready && tray.tray_ready;
    if (!launch.launch_ready) {
      notes.push("surface_ready=false — launch package not ready");
    } else if (!tray.tray_ready) {
      notes.push(
        "surface_ready=false — tray action not ready (e.g. full_merge needs completed)",
      );
    } else {
      notes.push(
        `surface_ready=true · surface_action=${surface_action} (still pure intent)`,
      );
    }
  }

  // Re-assert honesty
  if (launch.live_dispatched !== false || launch.merge_executed !== false) {
    throw new Error("invariant: launch honesty flags must remain false");
  }
  if (
    tray != null &&
    (tray.live_dispatched !== false ||
      tray.merge_executed !== false ||
      tray.pack_dispatched !== false)
  ) {
    throw new Error("invariant: tray honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("pack_dispatched=false");

  return {
    launch,
    tray,
    surface_action,
    surface_ready,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    notes,
    authority: "reading_highlight_float_merge_tray_compose_advisory",
  };
}

export function formatReadingHighlightFloatMergeTraySummary(
  c: ReadingHighlightFloatMergeTrayCompose,
): string {
  return (
    `surface_ready=${c.surface_ready} · action=${c.surface_action} · ` +
    `launch_ready=${c.launch.launch_ready} · ` +
    `tray_ready=${c.tray ? c.tray.tray_ready : "n/a"} · ` +
    `live_dispatched=false · merge_executed=false`
  );
}
