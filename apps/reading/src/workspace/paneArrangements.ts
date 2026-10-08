/**
 * paneArrangements.ts — SPR-01 M6: numbered arrangements 1–0 per project
 * (R11; specs/antiek-keyboard-panes-agents-20261007/sprint-01-leader-key-tiling.html).
 *
 * The Omarchy mapping (refs/omarchy-herdr.md A2): SUPER+1..0 jumps to
 * workspace N, SUPER+SHIFT+1..0 moves the focused window to workspace N and
 * follows, SUPER+TAB / SUPER+SHIFT+TAB cycle EXISTING workspaces,
 * SUPER+CTRL+TAB is the last-used one. Here: prefix+digit / ctrl+alt+digit
 * jump, prefix+shift+digit / ctrl+alt+shift+digit move-and-follow,
 * prefix+tab / prefix+shift+tab cycle existing, prefix+ctrl+tab last-used.
 * Decision (the page's, recorded): prefix+digit is an ARRANGEMENT jump, not
 * herdr's tab jump — tabs keep n/p.
 *
 * A numbered preset is a presentation snapshot — { arrangement, order,
 * tiles }, zoom always null (R12 clears zoom on any arrangement change) —
 * keyed by the account project and kept in the layout owner
 * (WorkspaceStore), never a parallel pane model. A preset holds pane
 * TARGETS by identity: a target whose host is gone is dropped on apply with
 * an honesty event (console.warn, the persistence.ts idiom), never
 * substituted (S01/S09).
 *
 * Recorded deviation (the page is silent on an empty slot), revised after
 * the adversarial review of the first draft: jumping to a slot with no
 * preset RELOCATES the current view — its content takes slot N and the old
 * slot is vacated. "Save current as N" with single membership: a pane's
 * identity belongs to exactly one slot's preset after any operation (a copy
 * would list it on both, and visibleTargets would show it on both). Slots
 * are live mirrors: the current slot's preset tracks the live view
 * continuously (the mirror subscription in WorkspaceStore), so a reload
 * mid-arrangement loses nothing, and a jump is a pointer move plus an
 * apply.
 *
 * This module is pure: no store, no storage, no DOM. WorkspaceStore owns
 * the state; persistence.ts owns the blob.
 */
import type { PaneArrangement, PaneTarget, PaneTile } from "./panel.types";
import { paneKey, reconcilePaneOrder, reconcilePaneTiles, samePane } from "./paneFlowGeometry";

/** The ten slots, in cycling order: 1–9 then 0 (Omarchy's tenth workspace). */
export const ARRANGEMENT_SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"] as const;
export type ArrangementSlot = (typeof ARRANGEMENT_SLOTS)[number];

export function isArrangementSlot(value: unknown): value is ArrangementSlot {
  return typeof value === "string" && (ARRANGEMENT_SLOTS as readonly string[]).includes(value);
}

/** The flow arrangements only — a preset never records "legacy". */
export type PresetArrangement = Exclude<PaneArrangement, "legacy">;

export interface ArrangementPreset {
  arrangement: PresetArrangement;
  /** Pane targets by identity, in presentation order. */
  order: PaneTarget[];
  tiles: PaneTile | null;
}

export interface ProjectSlots {
  current: ArrangementSlot;
  last: ArrangementSlot | null;
  presets: Partial<Record<ArrangementSlot, ArrangementPreset>>;
}

/** projectId → its slots. */
export type PaneArrangementMap = Record<string, ProjectSlots>;

export function emptyProjectSlots(): ProjectSlots {
  return { current: "1", last: null, presets: {} };
}

/** Snapshot the live view as a preset. Zoom is never saved (R12). */
export function snapshotPreset(state: {
  paneArrangement: PaneArrangement;
  paneOrder: readonly PaneTarget[];
  paneTiles: PaneTile | null;
}): ArrangementPreset | null {
  if (state.paneArrangement === "legacy") return null;
  return { arrangement: state.paneArrangement, order: [...state.paneOrder], tiles: state.paneTiles };
}

/**
 * The pane targets a slot's view shows: every admitted host that is
 * unassigned (in no preset at all — a freshly opened window joins the
 * current view, Omarchy's "new window lands on the current workspace")
 * plus every member of the slot's preset. A target in another slot's
 * preset is parked with that slot, hidden until its slot is jumped to.
 * `slot` defaults to the project's current slot.
 */
export function visibleTargets(
  admitted: readonly PaneTarget[],
  project: ProjectSlots,
  slot: ArrangementSlot = project.current,
): PaneTarget[] {
  const assigned = new Set<string>();
  for (const preset of Object.values(project.presets)) {
    for (const target of preset?.order ?? []) assigned.add(paneKey(target));
  }
  if (assigned.size === 0) return [...admitted];
  const members = new Set((project.presets[slot]?.order ?? []).map(paneKey));
  return admitted.filter((target) => {
    const key = paneKey(target);
    return !assigned.has(key) || members.has(key);
  });
}

/**
 * Apply a preset over the admitted hosts: order and tiles reconcile against
 * what the slot's view may actually show. The visibility filter is folded
 * in HERE (not left to the caller): `project` + `slot` decide which admitted
 * panes are this slot's to show, so a preset can never resurrect a pane
 * parked on another slot (review hole 2 — reconcilePaneOrder appends any
 * admitted pane it is handed, so the filter must not be optional). A preset
 * target whose host is GONE is dropped and named in `dropped` (the caller
 * logs the honesty event); it is never substituted. A member admitted but
 * missing from the preset (drift) joins at the end rather than
 * disappearing.
 */
export function applyPreset(
  preset: ArrangementPreset,
  admitted: readonly PaneTarget[],
  project: ProjectSlots,
  slot: ArrangementSlot,
): { order: PaneTarget[]; tiles: PaneTile | null; dropped: string[] } {
  const visible = visibleTargets(admitted, project, slot);
  const visibleKeys = new Set(visible.map(paneKey));
  const dropped = preset.order.filter((target) => !visibleKeys.has(paneKey(target))).map(paneKey);
  const order = reconcilePaneOrder(preset.order, visible);
  return { order, tiles: reconcilePaneTiles(preset.tiles, order), dropped };
}

/** The next EXISTING slot after `current`, wrapping; empty slots — no
 *  preset, or a preset with no panes left in it — skip (hyprland's `e+1`
 *  cycles workspaces that have windows). Null when no other slot exists. */
export function nextExistingSlot(
  project: ProjectSlots,
  direction: 1 | -1,
): ArrangementSlot | null {
  const existing = new Set(
    Object.entries(project.presets)
      .filter(([, preset]) => (preset?.order.length ?? 0) > 0)
      .map(([slot]) => slot),
  );
  const at = ARRANGEMENT_SLOTS.indexOf(project.current);
  for (let step = 1; step < ARRANGEMENT_SLOTS.length; step++) {
    const candidate = ARRANGEMENT_SLOTS[(at + direction * step + ARRANGEMENT_SLOTS.length * step) % ARRANGEMENT_SLOTS.length];
    if (existing.has(candidate)) return candidate;
  }
  return null;
}

/**
 * Move a target between presets (SUPER+SHIFT+N): out of the source preset's
 * order/tiles, appended to the destination's (created empty with the
 * source's arrangement when the slot is fresh). Returns both presets, or
 * null when the target is not in the source.
 */
export function moveTargetBetweenPresets(
  source: ArrangementPreset,
  destination: ArrangementPreset | null,
  target: PaneTarget,
): { source: ArrangementPreset; destination: ArrangementPreset } | null {
  if (!source.order.some((member) => samePane(member, target))) return null;
  const sourceOrder = source.order.filter((member) => !samePane(member, target));
  // Single membership (review hole 3): a destination that already lists the
  // pane keeps its one entry — never a second.
  const destHas = destination?.order.some((member) => samePane(member, target)) ?? false;
  const destOrder = destHas ? destination!.order : [...(destination?.order ?? []), target];
  return {
    source: { ...source, order: sourceOrder, tiles: reconcilePaneTiles(source.tiles, sourceOrder) },
    destination: {
      arrangement: destination?.arrangement ?? source.arrangement,
      order: destOrder,
      tiles: reconcilePaneTiles(destination?.tiles ?? null, destOrder),
    },
  };
}

/** The target a pane key names, from a list (identity by key, not object). */
export function targetByKey(order: readonly PaneTarget[], key: string): PaneTarget | null {
  return order.find((member) => paneKey(member) === key) ?? null;
}
