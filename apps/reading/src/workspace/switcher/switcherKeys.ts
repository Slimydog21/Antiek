/**
 * switcherKeys.ts — SPR-04 M1: the pure reducer. `stepSwitcher` turns a
 * key (or a click, or a project's arrival) into the next ui state and at
 * most one named effect; it never touches a store (gearActions.ts runs the
 * effect). Omarchy's nested menu keys (refs/omarchy-herdr.md rule 14):
 * ←/→ (h/l) hop within a gear and never activate, Enter clicks in,
 * Backspace (or ← at the first tab) clicks back, Esc closes.
 */
import type { Gear, GearTab, SwitcherModel } from "./switcherModel";

export type SwitcherKey = "ArrowLeft" | "ArrowRight" | "Home" | "End" | "Enter" | "Backspace" | "Escape" | "h" | "l";

export type SwitcherInput =
  | SwitcherKey
  | { type: "project-arrived"; id: string }
  | { type: "click"; key: GearTab["key"] };

export interface SwitcherUi {
  gear: Gear;
  /** The roving-tabindex tab; null on an empty strip or when the next
   *  strip's tabs are not known yet (normalizeUi settles it). */
  cursor: GearTab["key"] | null;
  /** A project asked for at gear 1; its arrival clicks into gear 2. */
  awaitingProject: string | null;
}

export type GearEffect =
  | { type: "select-project"; id: string }
  | { type: "select-subproject"; id: string; route: string | null; label: string }
  | { type: "select-agent"; id: string; viewId: string; viewOpen: boolean; kind: GearTab["agent"] extends infer A ? A extends { kind: infer K } ? K : never : never; investigationId?: string; scope: NonNullable<GearTab["agent"]>["scope"]; label: string }
  | { type: "close" }
  | { type: "notch" };

export interface SwitcherStep {
  ui: SwitcherUi;
  effect: GearEffect | null;
}

function stripOf(model: SwitcherModel, gear: Gear) {
  return model.strips[gear - 1];
}

/** The strip's selected tab, else its first, else null. */
function restingCursor(model: SwitcherModel, gear: Gear): GearTab["key"] | null {
  const s = stripOf(model, gear);
  return s.tabs.find((t) => t.selected)?.key ?? s.tabs[0]?.key ?? null;
}

/** Gear 1, cursor on the selected project (else the first root). */
export function openUi(model: SwitcherModel): SwitcherUi {
  return { gear: 1, cursor: restingCursor(model, 1), awaitingProject: null };
}

/** A cursor that is not in the current strip (a republished tree, a strip
 *  the reducer could not see yet) rests on the selected-or-first tab. */
export function normalizeUi(model: SwitcherModel, ui: SwitcherUi): SwitcherUi {
  const s = stripOf(model, ui.gear);
  if (ui.cursor !== null && s.tabs.some((t) => t.key === ui.cursor)) return ui;
  const cursor = restingCursor(model, ui.gear);
  return cursor === ui.cursor ? ui : { ...ui, cursor };
}

function back(model: SwitcherModel, ui: SwitcherUi): SwitcherStep {
  if (ui.gear === 1) return { ui, effect: { type: "notch" } };
  const gear = (ui.gear - 1) as Gear;
  return { ui: { gear, cursor: restingCursor(model, gear), awaitingProject: ui.awaitingProject }, effect: null };
}

function enter(model: SwitcherModel, ui: SwitcherUi): SwitcherStep {
  const s = stripOf(model, ui.gear);
  const tab = s.tabs.find((t) => t.key === ui.cursor);
  if (!tab) return { ui, effect: { type: "notch" } };
  if (ui.gear === 1) {
    if (tab.selected) return { ui: { gear: 2, cursor: restingCursor(model, 2), awaitingProject: null }, effect: null };
    return { ui: { ...ui, awaitingProject: tab.id }, effect: { type: "select-project", id: tab.id } };
  }
  if (tab.role === "subproject") {
    // Gear 2 clicks into gear 3; a gear-3 node tab drills and stays at 3.
    // The next strip depends on the selection write, so the cursor settles
    // once the model has it (normalizeUi).
    return {
      ui: { gear: 3, cursor: null, awaitingProject: null },
      effect: { type: "select-subproject", id: tab.id, route: tab.node?.route ?? null, label: tab.label },
    };
  }
  const a = tab.agent!;
  return {
    ui,
    effect: {
      type: "select-agent", id: tab.id, viewId: a.viewId, viewOpen: a.viewOpen, kind: a.kind,
      ...(a.investigationId !== undefined ? { investigationId: a.investigationId } : {}),
      scope: a.scope, label: tab.label,
    },
  };
}

export function stepSwitcher(model: SwitcherModel, ui: SwitcherUi, input: SwitcherInput): SwitcherStep {
  if (typeof input !== "string") {
    if (input.type === "click") {
      const s = stripOf(model, ui.gear);
      if (!s.tabs.some((t) => t.key === input.key)) return { ui, effect: null };
      return enter(model, { ...ui, cursor: input.key });
    }
    // project-arrived
    if (ui.awaitingProject !== null && input.id === ui.awaitingProject) {
      return { ui: { gear: 2, cursor: restingCursor(model, 2), awaitingProject: null }, effect: null };
    }
    return { ui: ui.awaitingProject === null ? ui : { ...ui, awaitingProject: null }, effect: null };
  }
  const s = stripOf(model, ui.gear);
  const idx = s.tabs.findIndex((t) => t.key === ui.cursor);
  const at = (i: number): SwitcherStep => ({ ui: { ...ui, cursor: s.tabs[i]?.key ?? null }, effect: null });
  switch (input) {
    case "ArrowRight":
    case "l":
      if (s.tabs.length === 0) return { ui: { ...ui, cursor: null }, effect: null };
      return at(idx === -1 ? 0 : Math.min(idx + 1, s.tabs.length - 1));
    case "ArrowLeft":
    case "h":
      if (idx > 0) return at(idx - 1);
      return back(model, ui);
    case "Home":
      return at(0);
    case "End":
      return at(s.tabs.length - 1);
    case "Backspace":
      return back(model, ui);
    case "Enter":
      return enter(model, ui);
    case "Escape":
      return { ui, effect: { type: "close" } };
  }
}
