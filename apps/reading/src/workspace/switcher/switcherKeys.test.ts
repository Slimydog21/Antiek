/**
 * switcherKeys.test.ts — SPR-04 M1: the pure reducer over every reachable
 * ui state of every seeded model. The reducer never touches a store; it
 * names an effect and the surface runs it (gearActions.ts).
 */
import { describe, expect, it } from "vitest";

import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { fixtureInputs } from "../contracts/fixtures.test.helpers";
import { SEEDS, genTree, selectionsFor } from "./switcherFixtures.test.helpers";
import { normalizeUi, openUi, stepSwitcher, type SwitcherInput, type SwitcherKey, type SwitcherUi } from "./switcherKeys";
import { deriveSwitcher, type Gear, type SwitcherModel } from "./switcherModel";

const KEYS: SwitcherKey[] = ["ArrowLeft", "ArrowRight", "Home", "End", "Enter", "Backspace", "Escape", "h", "l"];

function stripOf(m: SwitcherModel, ui: SwitcherUi) {
  return m.strips[ui.gear - 1];
}
function indexOf(m: SwitcherModel, ui: SwitcherUi): number {
  return stripOf(m, ui).tabs.findIndex((t) => t.key === ui.cursor);
}
function selectedKeyOf(m: SwitcherModel, gear: Gear): string | null {
  const s = m.strips[gear - 1];
  return s.tabs.find((t) => t.selected)?.key ?? s.tabs[0]?.key ?? null;
}
/** Every ui state: each gear × each cursor (every key and null) × awaiting. */
function states(m: SwitcherModel): SwitcherUi[] {
  const out: SwitcherUi[] = [];
  for (const gear of [1, 2, 3] as const) {
    const keys = [...m.strips[gear - 1].tabs.map((t) => t.key), null];
    for (const cursor of keys) for (const awaitingProject of [null, "p-await"]) out.push({ gear, cursor, awaitingProject });
  }
  return out;
}

describe("stepSwitcher — invariants over every ui state of 200 seeded models", () => {
  it.each(SEEDS)("seed %i", (seed) => {
    const tree = genTree(seed);
    const { valid, stale } = selectionsFor(tree);
    for (const sel of [...valid.slice(0, 12), ...stale.slice(0, 1)]) {
      const m = deriveSwitcher(tree, sel);
      // openUi: always gear 1, cursor on the selected project, else the first root.
      const opened = openUi(m);
      expect(opened.gear).toBe(1);
      expect(opened.awaitingProject).toBeNull();
      expect(opened.cursor).toBe(m.strips[0].tabs.find((t) => t.selected)?.key ?? m.strips[0].tabs[0]?.key ?? null);
      for (const ui of states(m)) {
        const strip = stripOf(m, ui);
        const idx = indexOf(m, ui);
        for (const key of KEYS) {
          const { ui: next, effect } = stepSwitcher(m, ui, key);
          // The cursor is always in the current strip or null.
          const nextStrip = stripOf(m, next);
          expect(next.cursor === null || nextStrip.tabs.some((t) => t.key === next.cursor)).toBe(true);
          expect([1, 2, 3]).toContain(next.gear);
          if (key === "Escape") {
            expect(effect).toEqual({ type: "close" });
            expect(next).toEqual(ui);
          }
          if (key === "ArrowRight" || key === "l") {
            expect(effect).toBeNull();
            expect(next.gear).toBe(ui.gear);
            if (strip.tabs.length === 0) expect(next.cursor).toBeNull();
            else if (idx === -1) expect(next.cursor).toBe(strip.tabs[0].key);
            else expect(next.cursor).toBe(strip.tabs[Math.min(idx + 1, strip.tabs.length - 1)].key); // clamped, no wrap
          }
          if (key === "Home" || key === "End") {
            expect(effect).toBeNull();
            expect(next.gear).toBe(ui.gear);
            expect(next.cursor).toBe(strip.tabs.length ? (key === "Home" ? strip.tabs[0] : strip.tabs.at(-1)!).key : null);
          }
          if (key === "ArrowLeft" || key === "h") {
            if (idx > 0) {
              expect(effect).toBeNull();
              expect(next.gear).toBe(ui.gear);
              expect(next.cursor).toBe(strip.tabs[idx - 1].key);
            } else {
              // At index 0 (or no cursor): back one gear, like Backspace.
              expect({ ui: next, effect }).toEqual(stepSwitcher(m, ui, "Backspace"));
            }
          }
          if (key === "Backspace") {
            if (ui.gear === 1) {
              expect(effect).toEqual({ type: "notch" });
              expect(next).toEqual(ui);
            } else {
              expect(effect).toBeNull();
              expect(next.gear).toBe(ui.gear - 1);
              expect(next.cursor).toBe(selectedKeyOf(m, (ui.gear - 1) as Gear));
              if (ui.gear === 2) expect(next.cursor).toBe(m.strips[0].tabs.find((t) => t.selected)?.key ?? m.strips[0].tabs[0]?.key ?? null);
              if (ui.gear === 3) {
                const depth1 = m.path.find((t) => t.role === "subproject");
                expect(next.cursor).toBe(depth1 ? depth1.key : m.strips[1].tabs[0]?.key ?? null);
              }
            }
          }
          if (key === "Enter") {
            if (idx === -1) {
              expect(effect).toEqual({ type: "notch" });
              expect(next).toEqual(ui);
            } else {
              const tab = strip.tabs[idx];
              if (ui.gear === 1) {
                if (tab.selected) {
                  expect(effect).toBeNull();
                  expect(next.gear).toBe(2);
                  expect(next.cursor).toBe(selectedKeyOf(m, 2));
                } else {
                  expect(effect).toEqual({ type: "select-project", id: tab.id });
                  expect(next).toEqual({ ...ui, awaitingProject: tab.id });
                }
              } else if (ui.gear === 2) {
                expect(effect).toEqual({ type: "select-subproject", id: tab.id, route: tab.node!.route, label: tab.label });
                expect(next).toEqual({ gear: 3, cursor: null, awaitingProject: null });
              } else if (tab.role === "subproject") {
                expect(effect).toEqual({ type: "select-subproject", id: tab.id, route: tab.node!.route, label: tab.label });
                expect(next).toEqual({ gear: 3, cursor: null, awaitingProject: null });
              } else {
                expect(effect).toEqual({
                  type: "select-agent", id: tab.id, viewId: tab.agent!.viewId, viewOpen: tab.agent!.viewOpen, kind: tab.agent!.kind,
                  ...(tab.agent!.investigationId !== undefined ? { investigationId: tab.agent!.investigationId } : {}),
                  scope: tab.agent!.scope, label: tab.label,
                });
                expect(next).toEqual(ui);
              }
            }
          }
        }
        // Right then Left round-trips when Right moved; End then Right stays.
        if (idx >= 0 && idx < strip.tabs.length - 1) {
          const r = stepSwitcher(m, ui, "ArrowRight").ui;
          expect(stepSwitcher(m, r, "ArrowLeft").ui).toEqual(r.cursor === strip.tabs[0].key ? r : { ...ui });
        }
        const end = stepSwitcher(m, ui, "End").ui;
        expect(stepSwitcher(m, end, "ArrowRight").ui).toEqual(end);
        // click ≡ cursor move + Enter; a key not in the strip is a no-op.
        for (const t of strip.tabs) {
          expect(stepSwitcher(m, ui, { type: "click", key: t.key })).toEqual(stepSwitcher(m, { ...ui, cursor: t.key }, "Enter"));
        }
        expect(stepSwitcher(m, ui, { type: "click", key: "project:not-a-tab" })).toEqual({ ui, effect: null });
        // project-arrived: the awaited id clicks into gear 2; any other id only clears the wait.
        const arrived = stepSwitcher(m, { ...ui, awaitingProject: "p-await" }, { type: "project-arrived", id: "p-await" });
        expect(arrived.effect).toBeNull();
        expect(arrived.ui).toEqual({ gear: 2, cursor: m.strips[1].tabs.find((t) => t.selected)?.key ?? m.strips[1].tabs[0]?.key ?? null, awaitingProject: null });
        const other = stepSwitcher(m, { ...ui, awaitingProject: "p-await" }, { type: "project-arrived", id: "someone-else" });
        expect(other).toEqual({ ui: { ...ui, awaitingProject: null }, effect: null });
        expect(stepSwitcher(m, { ...ui, awaitingProject: null }, { type: "project-arrived", id: "p-await" })).toEqual({ ui: { ...ui, awaitingProject: null }, effect: null });
        // normalizeUi puts a lost cursor back on the strip's selected-or-first tab.
        const norm = normalizeUi(m, ui);
        expect(norm.cursor).toBe(idx >= 0 ? ui.cursor : selectedKeyOf(m, ui.gear));
        expect(normalizeUi(m, { ...ui, cursor: "agent:nobody" }).cursor).toBe(selectedKeyOf(m, ui.gear));
      }
    }
  });
});

describe("stepSwitcher — the named journey on the shared fixture", () => {
  const tree = composePreBackendTree(fixtureInputs());
  const sel = { projectId: "default" as const };
  const m = deriveSwitcher(tree, sel);
  const run = (ui: SwitcherUi, ...inputs: SwitcherInput[]) => inputs.reduce((acc, i) => ({ ...stepSwitcher(m, acc.ui, i) }), { ui, effect: null as ReturnType<typeof stepSwitcher>["effect"] });

  it("opens at gear 1 on the current project; Enter clicks into gear 2 without an effect", () => {
    const ui = openUi(m);
    expect(ui).toEqual({ gear: 1, cursor: "project:default", awaitingProject: null });
    const { ui: g2, effect } = stepSwitcher(m, ui, "Enter");
    expect(effect).toBeNull();
    expect(g2.gear).toBe(2);
    expect(g2.cursor).toBe(m.strips[1].tabs[0].key);
  });

  it("Enter on another project asks for it and waits; its arrival clicks into gear 2", () => {
    const { ui, effect } = run(openUi(m), "ArrowRight", "Enter");
    expect(effect).toEqual({ type: "select-project", id: "p1" });
    expect(ui).toEqual({ gear: 1, cursor: "project:p1", awaitingProject: "p1" });
    const m2 = deriveSwitcher(tree, { projectId: "p1" });
    const arrived = stepSwitcher(m2, ui, { type: "project-arrived", id: "p1" });
    expect(arrived.ui).toEqual({ gear: 2, cursor: null, awaitingProject: null });
    expect(m2.strips[1].empty).toBe("not-linked");
    expect(stepSwitcher(m2, arrived.ui, "Enter")).toEqual({ ui: arrived.ui, effect: { type: "notch" } });
  });

  it("gear 2 Enter opens the investigation; gear 3 lists its children and the agents; Backspace lands on the gear-2 tab", () => {
    const { ui: g2 } = run(openUi(m), "Enter");
    expect(g2.cursor).toBe("subproject:inv-root");
    const { ui: g3, effect } = stepSwitcher(m, g2, "Enter");
    expect(effect).toEqual({ type: "select-subproject", id: "inv-root", route: "/inv/inv-root", label: "Question inv-root" });
    const m3 = deriveSwitcher(tree, { projectId: "default", subProjectId: "inv-root" });
    const ui3 = normalizeUi(m3, g3);
    expect(ui3).toEqual({ gear: 3, cursor: "subproject:inv-child-2", awaitingProject: null });
    expect(m3.strips[2].tabs.map((t) => t.key)).toEqual([
      "subproject:inv-child-2", "subproject:inv-child",
      "agent:inv-child", "agent:agent:dialogue", "agent:inv-unknown", "agent:inv-member",
    ]);
    const back = stepSwitcher(m3, ui3, "Backspace");
    expect(back.ui).toEqual({ gear: 2, cursor: "subproject:inv-root", awaitingProject: null });
    const agent = stepSwitcher(m3, { ...ui3, cursor: "agent:inv-child" }, "Enter");
    expect(agent.effect).toMatchObject({ type: "select-agent", id: "inv-child", viewId: "agent:thread:inv-child", viewOpen: true, kind: "research-thread", investigationId: "inv-child", scope: "cross-project" });
    expect(agent.ui).toEqual({ ...ui3, cursor: "agent:inv-child" });
  });

  it("Backspace at gear 1 notches; Escape closes", () => {
    expect(stepSwitcher(m, openUi(m), "Backspace")).toEqual({ ui: openUi(m), effect: { type: "notch" } });
    expect(stepSwitcher(m, openUi(m), "Escape")).toEqual({ ui: openUi(m), effect: { type: "close" } });
  });
});
