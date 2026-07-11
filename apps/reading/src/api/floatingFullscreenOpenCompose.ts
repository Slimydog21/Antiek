/**
 * Floating deep research → open fullscreen compose (pure).
 *
 * Operator vision: spin up a deep-research instance from a highlight (or use
 * an existing float), select it in the tray, and open fullscreen — without
 * live dispatch or parent merge.
 *
 * live_dispatched always false.
 * merge_executed always false.
 * pack_dispatched always false.
 */

import {
  spawnFloatingFromHighlight,
  type FloatingDeepResearchInstance,
} from "./floatingDeepResearch";
import {
  composeFloatingInstanceTray,
  type FloatingInstanceTrayCompose,
  type TrayMember,
} from "./floatingInstanceTrayCompose";
import {
  composeFloatingResearchViewMode,
  type FloatingResearchViewModeCompose,
} from "./floatingResearchViewModeCompose";

export interface FloatingFullscreenOpenInput {
  session_id: string;
  parent_asset_id: string;
  /**
   * When provided, open this existing instance (must share parent).
   * When omitted, spawn from highlight (requires highlight + gated).
   */
  existing_instance?: FloatingDeepResearchInstance | null;
  /** Required when spawning (no existing_instance). */
  highlight?: string | null;
  prompt?: string | null;
  /**
   * Provenance gate from highlight. Required when spawning.
   * Must be false to spawn (fail closed).
   */
  gated?: boolean | null;
  /** Optional sibling tray members (same parent); selected is always the target. */
  tray_siblings?: TrayMember[] | null;
  operator_ack: boolean;
}

export interface FloatingFullscreenOpenCompose {
  session_id: string;
  parent_asset_id: string;
  instance: FloatingDeepResearchInstance;
  tray: FloatingInstanceTrayCompose;
  view_mode: FloatingResearchViewModeCompose;
  /**
   * True when tray fullscreen_one ready and view-mode fullscreen applied.
   * Still never dispatches live research.
   */
  fullscreen_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  notes: string[];
  authority: "floating_fullscreen_open_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose highlight/spawn → tray select → fullscreen open intent.
 * Never live-dispatches; never merges parent.
 */
export function composeFloatingFullscreenOpen(
  input: FloatingFullscreenOpenInput,
): FloatingFullscreenOpenCompose {
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
    "live_dispatched=false — fullscreen is view-mode intent only",
    "merge_executed=false — parent asset not mutated",
    "pack_dispatched=false — no collective pack from this path",
  ];

  let instance: FloatingDeepResearchInstance;
  if (input.existing_instance != null) {
    instance = input.existing_instance;
    if (!instance || typeof instance !== "object") {
      throw new Error("existing_instance must be an object when set");
    }
    if (instance.parent_asset_id.trim() !== parent_asset_id) {
      throw new Error("existing_instance.parent_asset_id must match parent");
    }
    if (instance.live_dispatched !== false) {
      throw new Error("existing_instance.live_dispatched must be false");
    }
    if (instance.merge_executed !== false) {
      throw new Error("existing_instance.merge_executed must be false");
    }
    if (instance.status === "closed") {
      throw new Error("cannot fullscreen a closed instance");
    }
    notes.push(
      `using existing_instance=${instance.instance_id} status=${instance.status}`,
    );
  } else {
    if (typeof input.gated !== "boolean") {
      throw new Error(
        "gated must be an explicit boolean when spawning from highlight",
      );
    }
    const highlight = requireNonEmpty(input.highlight, "highlight");
    instance = spawnFloatingFromHighlight({
      parent_asset_id,
      highlight,
      prompt:
        input.prompt != null && String(input.prompt).trim()
          ? String(input.prompt).trim()
          : undefined,
      gated: input.gated,
      view_mode: "floating",
    });
    notes.push(
      `spawned floating instance=${instance.instance_id} from highlight`,
    );
  }

  const siblings: TrayMember[] =
    input.tray_siblings != null
      ? input.tray_siblings.map((m) => ({ ...m }))
      : [];
  // Ensure target is in members
  const members: TrayMember[] = [
    {
      instance_id: instance.instance_id,
      parent_asset_id: instance.parent_asset_id,
      status: instance.status,
      highlight: instance.highlight,
      view_mode: instance.view_mode,
      live_dispatched: false,
      merge_executed: false,
    },
    ...siblings.filter((m) => m.instance_id !== instance.instance_id),
  ];

  const tray = composeFloatingInstanceTray({
    parent_asset_id,
    members,
    selected_instance_ids: [instance.instance_id],
    action: "fullscreen_one",
    operator_ack: input.operator_ack,
  });
  notes.push(...tray.notes.map((n) => `[tray] ${n}`));

  const view_mode = composeFloatingResearchViewMode({
    instance,
    action: "fullscreen",
    operator_ack: input.operator_ack,
  });
  notes.push(...view_mode.notes.map((n) => `[view] ${n}`));

  const fullscreen_ready =
    tray.tray_ready === true &&
    view_mode.action_applied === true &&
    view_mode.view_mode === "fullscreen" &&
    input.operator_ack === true;

  if (fullscreen_ready) {
    notes.push(
      "fullscreen_ready=true — open fullscreen intent ready; still pure",
    );
  } else {
    notes.push(
      "fullscreen_ready=false — tray, view-mode, or operator_ack gate open",
    );
  }

  if (
    tray.live_dispatched !== false ||
    tray.merge_executed !== false ||
    tray.pack_dispatched !== false ||
    view_mode.live_dispatched !== false ||
    view_mode.merge_executed !== false ||
    view_mode.instance.live_dispatched !== false ||
    view_mode.instance.merge_executed !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    parent_asset_id,
    instance: view_mode.instance,
    tray,
    view_mode,
    fullscreen_ready,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    notes,
    authority: "floating_fullscreen_open_compose_advisory",
  };
}

export function formatFloatingFullscreenOpenSummary(
  c: FloatingFullscreenOpenCompose,
): string {
  return (
    `fullscreen_ready=${c.fullscreen_ready} · ` +
    `view_mode=${c.instance.view_mode} · ` +
    `instance=${c.instance.instance_id} · ` +
    `live_dispatched=false · merge_executed=false · pack_dispatched=false`
  );
}
