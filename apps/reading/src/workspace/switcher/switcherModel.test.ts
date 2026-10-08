/**
 * switcherModel.test.ts — SPR-04 M1: the gears are a pure function of the
 * SPR-06 tree and selection. Property-tested over 200 seeded trees from the
 * real pre-backend adapter: every gear-2 tab's parent is the selected root,
 * every gear-3 node tab's parent is the deepest node on the selected path
 * (the literal "selected in gear N-1" holds up to depth 1 and is a recorded
 * deviation beyond it, switcherModel.ts header; the chain block below
 * states and proves the property that actually holds), plus the named
 * degenerate cases (rigor #3) and the honesty cases (rigor #1: never
 * "Sub-project" pre-backend; an empty pre-backend gear 2 never asserts
 * absence).
 */
import { describe, expect, it } from "vitest";

import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { fixtureInputs, fixtureInputsWithMembers, project } from "../contracts/fixtures.test.helpers";
import { isSelectionPathOf, type Selection } from "../contracts/selection";
import { findAgent, findProjectPath, type ContextTree, type ProjectNode } from "../contracts/tree";
import { EMPTY_TREE, markTreeLoading, publishTree, useContextTreeStore } from "../contracts/treeStore";
import { useTabTrees } from "../tabTreeStore";
import { SEEDS, allNodes, deepFreeze, genTree, selectionsFor } from "./switcherFixtures.test.helpers";
import { deriveSwitcher, gearHeading, type GearStrip, type GearTab, type SwitcherModel } from "./switcherModel";

const subprojectTabs = (s: GearStrip) => s.tabs.filter((t) => t.role === "subproject");
const agentTabs = (s: GearStrip) => s.tabs.filter((t) => t.role === "agent");
const allText = (m: SwitcherModel) => [
  ...m.strips.map((s) => s.heading),
  ...m.strips.flatMap((s) => s.tabs.map((t) => t.kindLabel)),
  ...m.path.map((t) => `${t.kindLabel} ${t.label}`),
].join("\n");

function deepest(tree: ContextTree, sel: Selection): ProjectNode | null {
  return findProjectPath(tree, sel.subProjectId ?? sel.projectId)?.at(-1) ?? null;
}

describe("deriveSwitcher — invariants over 200 seeded adapter trees", () => {
  it.each(SEEDS)("seed %i", (seed) => {
    const tree = deepFreeze(genTree(seed));
    const { valid, stale } = selectionsFor(tree);
    expect(valid.length).toBeGreaterThan(0);
    for (const sel of valid) {
      const m = deriveSwitcher(tree, deepFreeze({ ...sel }));
      expect(m.status).toBe("ready");
      expect(m.error).toBeNull();
      const [g1, g2, g3] = m.strips;
      expect([g1.gear, g2.gear, g3.gear]).toEqual([1, 2, 3]);
      // Gear 1 is the forest's roots, the selected one lit.
      expect(g1.tabs.map((t) => t.id)).toEqual(tree.roots.map((r) => r.id));
      expect(g1.tabs.filter((t) => t.selected).map((t) => t.id)).toEqual([sel.projectId]);
      // Every gear-2 tab's parent is the selected project.
      for (const t of g2.tabs) {
        expect(t.role).toBe("subproject");
        expect(t.parentId).toBe(sel.projectId);
      }
      // Gear-2 selected = the depth-1 node on the path, never a deeper one.
      const path = findProjectPath(tree, sel.subProjectId ?? sel.projectId)!;
      expect(g2.tabs.filter((t) => t.selected).map((t) => t.id)).toEqual(path[1] ? [path[1].id] : []);
      expect(m.path.map((t) => t.id)).toEqual([...path.map((n) => n.id), ...(sel.agentId !== undefined ? [sel.agentId] : [])]);
      // Gear-3 node tabs are the deepest selected node's children; the
      // deepest node is on the path.
      const deep = deepest(tree, sel)!;
      expect(path.some((n) => n.id === deep.id)).toBe(true);
      for (const t of subprojectTabs(g3)) {
        expect(t.parentId).toBe(deep.id);
        expect(t.selected).toBe(false);
      }
      if (sel.subProjectId === undefined) expect(subprojectTabs(g3)).toEqual([]);
      else expect(subprojectTabs(g3).map((t) => t.id)).toEqual(deep.children.map((c) => c.id));
      // Every gear-3 agent is one the contract admits on this path.
      for (const t of agentTabs(g3)) {
        expect(isSelectionPathOf({ ...sel, agentId: t.id }, tree)).toBe(true);
        expect(t.agent).toBeDefined();
        expect(t.agent!.viewId).toBe(findAgent(tree, t.id)!.node.viewId);
      }
      expect(agentTabs(g3).map((t) => t.id)).toEqual([...deep.agents.map((a) => a.id), ...tree.crossProjectAgents.map((a) => a.id)]);
      // The divider sits at the first cross-project agent.
      if (tree.crossProjectAgents.length) {
        expect(g3.crossProjectFrom).toBe(g3.tabs.findIndex((t) => t.agent?.scope === "cross-project"));
        for (const t of g3.tabs.slice(g3.crossProjectFrom!)) expect(t.agent?.scope).toBe("cross-project");
      } else expect(g3.crossProjectFrom).toBeNull();
      expect(agentTabs(g3).filter((t) => t.selected).map((t) => t.id)).toEqual(
        sel.agentId !== undefined && agentTabs(g3).some((t) => t.id === sel.agentId) ? [sel.agentId] : [],
      );
      // No node id carries the subproject role in two strips; keys unique per strip.
      const g2ids = new Set(subprojectTabs(g2).map((t) => t.id));
      for (const t of subprojectTabs(g3)) expect(g2ids.has(t.id)).toBe(false);
      for (const s of m.strips) expect(new Set(s.tabs.map((t) => t.key)).size).toBe(s.tabs.length);
      for (const s of m.strips) for (const t of s.tabs) expect(t.key).toBe(`${t.role}:${t.id}`);
      // Selected only if the tree holds the id at that role.
      for (const s of m.strips) for (const t of s.tabs.filter((x) => x.selected)) {
        if (t.role === "project") expect(tree.roots.some((r) => r.id === t.id)).toBe(true);
        if (t.role === "subproject") expect(findProjectPath(tree, t.id)?.at(-1)?.kind).toBe("subproject");
        if (t.role === "agent") expect(findAgent(tree, t.id)).not.toBeNull();
      }
      // Empty strips say why; non-empty strips say nothing.
      for (const s of m.strips) expect(s.empty === null).toBe(s.tabs.length > 0);
      if (g2.tabs.length === 0) {
        const root = path[0];
        expect(g2.empty).toBe(root.source.kind === "registry" ? "not-linked" : "none-listed");
      }
      if (g3.tabs.length === 0) expect(g3.empty).toBe("no-agents");
      // Routes: an investigation node routes to /inv/<id>; nothing else routes.
      for (const s of m.strips) for (const t of s.tabs) {
        if (t.node) {
          const n = findProjectPath(tree, t.id)!.at(-1)!;
          expect(t.node.route).toBe(n.source.kind === "investigation" ? `/inv/${t.id}` : null);
          expect(t.node.sourceKind).toBe(n.source.kind);
          expect(t.node.provenance).toBe("pre-backend");
        }
      }
      // Pre-backend provenance never wears the sub-project costume (rigor #1).
      expect(allText(m)).not.toContain("Sub-project");
      // Deterministic and pure: the same answer twice, inputs untouched.
      expect(deriveSwitcher(tree, sel)).toEqual(m);
    }
    for (const sel of stale) {
      const m = deriveSwitcher(tree, deepFreeze({ ...sel }));
      expect(m.status).toBe("stale");
      expect(m.path).toEqual([]);
      for (const s of m.strips) for (const t of s.tabs) expect(t.selected).toBe(false);
      expect(m.strips[0].tabs.map((t) => t.id)).toEqual(tree.roots.map((r) => r.id));
      expect(m.strips[1]).toMatchObject({ tabs: [], empty: "stale-project" });
      expect(m.strips[2]).toMatchObject({ tabs: [], empty: "stale-project" });
    }
    expect(Object.isFrozen(tree)).toBe(true);
  });
});

describe("deriveSwitcher — the named fixtures", () => {
  it("the pre-backend id overlap: subproject:inv-child is not selected while agent:inv-child is", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers());
    const m = deriveSwitcher(tree, { projectId: "default", subProjectId: "inv-root", agentId: "inv-child" });
    const g3 = m.strips[2];
    expect(g3.tabs.find((t) => t.key === "subproject:inv-child")?.selected).toBe(false);
    expect(g3.tabs.find((t) => t.key === "agent:inv-child")?.selected).toBe(true);
    expect(m.strips[1].tabs.find((t) => t.key === "subproject:inv-root")?.selected).toBe(true);
    expect(m.path.map((t) => t.key)).toEqual(["project:default", "subproject:inv-root", "agent:inv-child"]);
    expect(m.path.map((t) => t.kindLabel)).toEqual(["Default project", "Investigation", "Agent"]);
  });

  it("a registry project pre-backend is 'not-linked'; a Default with nothing listed is 'none-listed'; backend is 'no-children'", () => {
    const pre = composePreBackendTree(fixtureInputs());
    expect(deriveSwitcher(pre, { projectId: "p2" }).strips[1]).toMatchObject({ tabs: [], empty: "not-linked", heading: "Investigations" });
    const bare = composePreBackendTree(fixtureInputs({ investigations: [], companionTabs: [] }));
    expect(deriveSwitcher(bare, { projectId: "default" }).strips[1]).toMatchObject({ tabs: [], empty: "none-listed", heading: "Investigations" });
    expect(deriveSwitcher(bare, { projectId: "default" }).strips[2]).toMatchObject({ tabs: [], empty: "no-agents" });
    // A backend-labelled registry forest (derived from the composed tree,
    // no hand-written node literal): the one shape allowed to say
    // "Sub-project", and "no-children" is then a true absence.
    const backend: ContextTree = {
      ...bare,
      provenance: "backend",
      roots: bare.roots.filter((r) => r.source.kind === "registry").map((r) => ({ ...r, provenance: "backend" as const })),
    };
    expect(deriveSwitcher(backend, { projectId: "p1" }).strips[1]).toMatchObject({ tabs: [], empty: "no-children", heading: "Investigations" });
  });

  it("gearHeading says 'Sub-projects' only for an all-backend list", () => {
    const pre = composePreBackendTree(fixtureInputs());
    const nodes = allNodes(pre).filter((n) => n.kind === "subproject");
    expect(nodes.length).toBeGreaterThan(0);
    expect(gearHeading(2, nodes)).toBe("Investigations");
    expect(gearHeading(2, [])).toBe("Investigations");
    expect(gearHeading(2, nodes.map((n) => ({ ...n, provenance: "backend" as const })))).toBe("Sub-projects");
    expect(gearHeading(2, [nodes[0], ...nodes.slice(1).map((n) => ({ ...n, provenance: "backend" as const }))])).toBe("Investigations");
    expect(gearHeading(1, [])).toBe("Projects");
    expect(gearHeading(3, [])).toBe("Agents");
  });

  it("EMPTY_TREE is 'unfed' three times, with an empty path", () => {
    const m = deriveSwitcher(EMPTY_TREE, { projectId: "default" });
    expect(m.status).toBe("unfed");
    expect(m.path).toEqual([]);
    expect(m.strips.map((s) => s.empty)).toEqual(["unfed", "unfed", "unfed"]);
    expect(m.strips.map((s) => s.tabs.length)).toEqual([0, 0, 0]);
  });

  it("a loading tree keeps its roots and reports loading; an empty strip says 'loading', never 'not in the list' or 'none listed'", () => {
    useTabTrees.getState().resetTabTrees();
    publishTree(composePreBackendTree(fixtureInputs()), "2026-10-07T22:40:00Z");
    markTreeLoading();
    const tree = useContextTreeStore.getState().tree;
    expect(tree.status).toBe("loading");
    const m = deriveSwitcher(tree, { projectId: "p2" });
    expect(m.status).toBe("loading");
    expect(m.strips[0].tabs.map((t) => t.id)).toEqual(["default", "p1", "p2"]);
    expect(m.strips[0].empty).toBeNull();
    expect(m.strips[1]).toMatchObject({ tabs: [], empty: "loading" });
    expect(m.strips[2].empty).toBe(m.strips[2].tabs.length ? null : "loading");
    // Status wins over stale: a stale selection on a loading tree is loading.
    expect(deriveSwitcher(tree, { projectId: "ghost" }).status).toBe("loading");
    expect(deriveSwitcher(tree, { projectId: "ghost" }).strips[1].empty).toBe("loading");
  });

  it("a refused publish surfaces as 'error' with the tree's message", () => {
    useTabTrees.getState().resetTabTrees();
    const good = composePreBackendTree(fixtureInputs());
    publishTree(good, "2026-10-07T22:40:00Z");
    publishTree({ ...good, roots: [good.roots[0], good.roots[0]] }, "2026-10-07T22:41:00Z");
    const tree = useContextTreeStore.getState().tree;
    expect(tree.status).toBe("error");
    const m = deriveSwitcher(tree, { projectId: "default" });
    expect(m.status).toBe("error");
    expect(m.error).toBe(tree.error);
    expect(m.error).toContain("publishTree refused");
    expect(m.strips[0].tabs.length).toBeGreaterThan(0);
  });

  it("the store's published tree and the raw composed tree derive the same gears (the 'both shapes' identity)", () => {
    useTabTrees.getState().resetTabTrees();
    const raw = composePreBackendTree(fixtureInputsWithMembers());
    publishTree(raw, "2026-10-07T22:40:00Z");
    const stored = useContextTreeStore.getState().tree;
    for (const sel of [...selectionsFor(raw).valid, ...selectionsFor(raw).stale]) {
      expect(deriveSwitcher(stored, sel)).toEqual(deriveSwitcher(raw, sel));
    }
  });

  it("production shape (no members fed, F3): every registry gear 2 is empty and every agent sits after the divider", () => {
    const tree = composePreBackendTree(fixtureInputs({ projects: [project("p1", "Varda diligence"), project("p2", "Second project"), project("p3", "Third")] }));
    for (const id of ["p1", "p2", "p3"]) {
      const m = deriveSwitcher(tree, { projectId: id });
      expect(m.strips[1]).toMatchObject({ tabs: [], empty: "not-linked" });
      expect(m.strips[2].crossProjectFrom).toBe(0);
      expect(m.strips[2].tabs.every((t) => t.agent?.scope === "cross-project")).toBe(true);
      expect(m.strips[2].tabs.length).toBe(tree.crossProjectAgents.length);
    }
  });

  it("the nested J3b journey (project → sub-project → agent on the path) is reachable only with members: a contrived fixture", () => {
    const withMembers = composePreBackendTree(fixtureInputsWithMembers());
    const nested = deriveSwitcher(withMembers, { projectId: "p1", subProjectId: "inv-member" });
    expect(nested.strips[1].tabs.map((t) => t.id)).toEqual(["inv-member"]);
    expect(nested.strips[2].tabs.find((t) => t.key === "agent:inv-member")?.agent?.scope).toBe("project");
    expect(nested.strips[2].crossProjectFrom).toBe(1);
    const without = composePreBackendTree(fixtureInputs());
    expect(deriveSwitcher(without, { projectId: "p1" }).strips[1].tabs).toEqual([]);
    expect(findProjectPath(without, "inv-member")![0].id).toBe("default");
  });

  it("the path carries kind-labelled entries the chip renders; a GearTab is a plain record", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const m = deriveSwitcher(tree, { projectId: "default", subProjectId: "inv-child" });
    const labels = m.path.map((t: GearTab) => `${t.kindLabel} ${t.label}`);
    expect(labels).toEqual(["Default project Default project", "Investigation Question inv-root", "Investigation Question inv-child"]);
    expect(m.strips[0].heading).toBe("Projects");
    expect(m.strips[2].heading).toBe("Agents");
  });
});

describe("rigor #3 — the gear chain, as it actually holds (repair round 2026-10-07T22:40Z)", () => {
  // The sprint page's literal wording, "every tab in gear N has its parent
  // selected in gear N-1", holds up to selection depth 1 and is a recorded
  // deviation beyond it (switcherModel.ts header): three gears over an
  // unbounded parent_investigation_id hierarchy cannot hold it at depth 2+
  // without hiding the deeper nodes. The property proven here is the one
  // the design keeps: a gear-N tab's parent is selected in gear N-1
  // whenever gear N-1 lists it, and is on the chip's selected path always.
  it.each(SEEDS)("seed %i", (seed) => {
    const tree = deepFreeze(genTree(seed));
    for (const sel of selectionsFor(tree).valid) {
      const m = deriveSwitcher(tree, sel);
      const [g1, g2, g3] = m.strips;
      const depth = m.path.filter((t) => t.role !== "agent").length - 1;
      const pathIds = new Set(m.path.filter((t) => t.role !== "agent").map((t) => t.id));
      const selectedIn = (s: GearStrip) => new Set(s.tabs.filter((t) => t.selected).map((t) => t.id));
      for (const t of g2.tabs) expect(selectedIn(g1).has(t.parentId!)).toBe(true);
      for (const t of g3.tabs) {
        if (t.agent?.scope === "cross-project") continue;
        expect(t.parentId).not.toBeNull();
        expect(pathIds.has(t.parentId!)).toBe(true);
        const listedInGear2 = g2.tabs.some((x) => x.id === t.parentId);
        if (depth <= 1) {
          // Literal rigor #3 at depth 0/1: the parent is the selected gear-2
          // tab (a sub-project) or the selected gear-1 root (depth 0).
          expect(depth === 0 ? selectedIn(g1).has(t.parentId!) : selectedIn(g2).has(t.parentId!)).toBe(true);
        } else {
          // The recorded deviation: the parent is the deepest path node,
          // a descendant of the selected gear-2 tab, not listed in gear 2.
          expect(listedInGear2).toBe(false);
          expect(t.parentId).toBe(m.path.filter((x) => x.role !== "agent").at(-1)!.id);
        }
      }
    }
  });

  it("the deviation is exercised, not vacuous: the seeds reach depth 2+ selections", () => {
    let deep = 0;
    for (const seed of SEEDS) {
      const tree = genTree(seed);
      for (const sel of selectionsFor(tree).valid) {
        if (deriveSwitcher(tree, sel).path.filter((t) => t.role !== "agent").length > 2) deep += 1;
      }
    }
    expect(deep).toBeGreaterThan(100);
  });
});
