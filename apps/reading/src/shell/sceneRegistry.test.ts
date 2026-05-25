import { describe, it, expect } from "vitest";

import { SCENE_REGISTRY, sceneForWorkflow } from "./sceneRegistry";
import type { SceneAction } from "./sceneRegistry";
import { tabSurface } from "./WorkflowStub";
import { WORKFLOWS } from "./workflowTaxonomy";

/**
 * SPR-05 — the scene registry is the durable interface SPR-07 + every future
 * product sprint register against. These tests pin its invariants so a future
 * descriptor can't ship broken: a `built` tab that links nowhere, a `soon` tab
 * masquerading as a destination, or a workflow with no chrome at all.
 *
 * The built-vs-soon honesty is the load-bearing one: a `built` tab MUST carry
 * a `to` route (it claims a real surface exists), and a tab can never be both
 * built and missing its route — that's the lie the stub exists to refuse.
 */

function intentIsValid(a: SceneAction): boolean {
  if (a.intent.kind === "navigate") {
    return typeof a.intent.to === "string" && a.intent.to.startsWith("/");
  }
  if (a.intent.kind === "event") {
    return typeof a.intent.event === "string" && a.intent.event.length > 0;
  }
  return false;
}

describe("sceneRegistry — every workflow has a usable descriptor", () => {
  it("covers all four workflows", () => {
    for (const w of WORKFLOWS) {
      expect(SCENE_REGISTRY[w], `${w} has no descriptor`).toBeDefined();
    }
    // exactly the four — no phantom workflows
    expect(Object.keys(SCENE_REGISTRY).sort()).toEqual([...WORKFLOWS].sort());
  });

  it("gives each workflow ≥1 action and ≥1 tab", () => {
    for (const w of WORKFLOWS) {
      const d = SCENE_REGISTRY[w];
      expect(d.actions.length, `${w} has no actions`).toBeGreaterThan(0);
      expect(d.tabs.length, `${w} has no tabs`).toBeGreaterThan(0);
    }
  });
});

describe("sceneRegistry — actions are functional (no dead intents)", () => {
  it("every action carries a valid navigate or event intent", () => {
    for (const w of WORKFLOWS) {
      for (const a of SCENE_REGISTRY[w].actions) {
        expect(intentIsValid(a), `${w}/${a.id} has an invalid intent`).toBe(true);
      }
    }
  });

  it("action ids are unique within a workflow", () => {
    for (const w of WORKFLOWS) {
      const ids = SCENE_REGISTRY[w].actions.map((a) => a.id);
      expect(new Set(ids).size, `${w} has duplicate action ids`).toBe(ids.length);
    }
  });
});

describe("sceneRegistry — built-vs-soon honesty", () => {
  it("every `built` tab carries a `to` route", () => {
    for (const w of WORKFLOWS) {
      for (const t of SCENE_REGISTRY[w].tabs) {
        if (t.builtState === "built") {
          expect(t.to, `${w}/${t.id} is built but has no route`).toBeTruthy();
          expect(t.to?.startsWith("/"), `${w}/${t.id} route is not absolute`).toBe(true);
        }
      }
    }
  });

  it("no tab is both built and missing its surface", () => {
    for (const w of WORKFLOWS) {
      for (const t of SCENE_REGISTRY[w].tabs) {
        const builtButRouteless = t.builtState === "built" && !t.to;
        expect(builtButRouteless, `${w}/${t.id} is built+routeless`).toBe(false);
      }
    }
  });

  it("tab ids are unique within a workflow", () => {
    for (const w of WORKFLOWS) {
      const ids = SCENE_REGISTRY[w].tabs.map((t) => t.id);
      expect(new Set(ids).size, `${w} has duplicate tab ids`).toBe(ids.length);
    }
  });

  it("at least one workflow exercises each builtState (chrome is exercisable now)", () => {
    const states = new Set(
      WORKFLOWS.flatMap((w) => SCENE_REGISTRY[w].tabs.map((t) => t.builtState)),
    );
    expect(states.has("built")).toBe(true);
    expect(states.has("soon")).toBe(true);
  });
});

describe("WorkflowStub.tabSurface — the stub/route flip is presence-driven", () => {
  it("routes a built tab, stubs a soon tab", () => {
    const built = SCENE_REGISTRY.research.tabs.find((t) => t.builtState === "built")!;
    const soon = SCENE_REGISTRY.read.tabs.find((t) => t.builtState === "soon")!;
    expect(tabSurface(built)).toEqual({ kind: "route", to: built.to });
    expect(tabSurface(soon)).toEqual({ kind: "stub" });
  });

  it("flips stub→route the moment a soon tab gains a built route (no hardcoded list)", () => {
    // Simulate SPR-07 shipping a surface: a soon tab gains a `to` + flips to
    // built. The same switch the Topbar reads — proving the stub decision is
    // computed, not a maintained list.
    const before = { id: "x", label: "X", builtState: "soon" as const };
    expect(tabSurface(before)).toEqual({ kind: "stub" });
    const after = { ...before, to: "/x", builtState: "built" as const };
    expect(tabSurface(after)).toEqual({ kind: "route", to: "/x" });
  });
});

describe("sceneForWorkflow — null on shared routes", () => {
  it("returns a descriptor for a workflow and null for shared", () => {
    expect(sceneForWorkflow("research")).toBe(SCENE_REGISTRY.research);
    expect(sceneForWorkflow(null)).toBeNull();
  });
});
