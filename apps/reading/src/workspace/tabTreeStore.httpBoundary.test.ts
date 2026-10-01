import { afterEach, beforeEach, expect, it, vi } from "vitest";
import fixture from "../lib/api/__fixtures__/projectTabs.snapshot.json";
import { parseTabsSnapshot, type TabsSnapshot } from "../lib/api/projectTabs";
import { setTabOwner } from "./tabTreeOwner";
import { tabsSaved, useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const drain = async () => { for (let i = 0; i < 120; i++) await Promise.resolve(); };
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
beforeEach(() => { setTabOwner(null); setTabOwner("wire-owner"); tabs().resetTabTrees(); });
afterEach(() => { setTabOwner(null); tabs().resetTabTrees(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("restores registered identity and both pane selections through HTTP, then reloads the accepted snapshot", async () => {
  const initial = parseTabsSnapshot(fixture.expected);
  const retired = initial.retired[0];
  const accepted = parseTabsSnapshot({
    ...initial,
    version: 3,
    active: { left: "t-agent-doc", right: retired.node.tab_id },
    tree: { nodes: { ...initial.tree.nodes, [retired.node.tab_id]: retired.node }, root_order: [...initial.tree.root_order, retired.node.tab_id] },
    retired: [],
  });
  let row = initial;
  const fetcher = vi.fn<typeof fetch>(async (_input, init) => {
    if (init?.method === "PUT") {
      expect(JSON.parse(String(init.body))).toEqual({ tree: accepted.tree, active: accepted.active, expected_version: 2 });
      row = accepted;
    } else {
      expect(init?.method).toBeUndefined();
    }
    return json(row);
  });
  vi.stubGlobal("fetch", fetcher);
  await tabs().bindActiveProject(async () => "wire-project");
  await tabs().ensureMothership("research");
  expect(tabs().undoLastClose("research")).toBe(true);
  await drain();
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  expect(tabs().trees.research!.nodes[retired.node.tab_id].public_number).toBe(4);
  expect(tabs().trees.research!.nodes[retired.node.tab_id].hier_number).toBe("3");
  expect(tabs().trees.research!.active_left).toBe("t-agent-doc");
  expect(tabs().trees.research!.active_right).toBe("t-dialogue");
  expect(tabsSaved(tabs())).toBe(true);
  tabs().resetTabTrees();
  await tabs().bindActiveProject(async () => "wire-project");
  await tabs().ensureMothership("research");
  expect(tabs().trees.research!.active_left).toBe("t-agent-doc");
  expect(tabs().trees.research!.active_right).toBe("t-dialogue");
  expect(tabs().trees.research!.history).toEqual({});
  expect(fetcher).toHaveBeenCalledTimes(3);
});

it("new tabs allocate project-wide across modes while existing null-number nodes stay unchanged", async () => {
  const initial = parseTabsSnapshot(fixture.expected);
  initial.tree.nodes["t-doc"].public_number = null;
  const rows = new Map<string, TabsSnapshot>([["research", initial]]);
  const requestedIds: string[] = [];
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path.endsWith("/allocate")) {
      const body: unknown = JSON.parse(String(init?.body));
      if (!body || typeof body !== "object" || !("tab_id" in body) || typeof body.tab_id !== "string") throw new Error("bad allocate body");
      requestedIds.push(body.tab_id);
      return json({ public_number: 4 + requestedIds.length });
    }
    const mode = path.split("/").at(-1);
    if (!mode) throw new Error("no mothership");
    const previous = rows.get(mode) ?? parseTabsSnapshot({ tree: { nodes: {}, root_order: [] }, active: { left: null, right: null }, version: 0, next_child_index: {}, retired: [] });
    if (init?.method === "PUT") {
      const body: unknown = JSON.parse(String(init.body));
      if (!body || typeof body !== "object" || !("tree" in body) || !("active" in body) || !("expected_version" in body)) throw new Error("bad PUT body");
      expect(body.expected_version).toBe(previous.version);
      const next_child_index = mode === "research" ? { ...previous.next_child_index, "t-doc": 2 } : { root: 2 };
      const accepted = parseTabsSnapshot({ ...previous, tree: body.tree, active: body.active, version: previous.version + 1, next_child_index });
      rows.set(mode, accepted);
      return json(accepted);
    }
    return json(previous);
  }));
  await tabs().bindActiveProject(async () => "wire-project");
  await tabs().ensureMothership("research");
  await tabs().ensureMothership("reading");
  tabs().spawnTab("research", "t-doc", { tab_id: "newResearch", kind: "reader", ref: "research-doc", mothership: "research", activate: true });
  await drain();
  tabs().spawnTab("reading", null, { tab_id: "newReading", kind: "reader", ref: "reading-doc", mothership: "reading", activate: true });
  await drain();
  expect(requestedIds).toEqual(["newResearch", "newReading"]);
  expect(tabs().trees.research!.nodes["t-doc"].public_number).toBeNull();
  expect(tabs().trees.research!.nodes.newResearch.public_number).toBe(5);
  expect(tabs().trees.reading!.nodes.newReading.public_number).toBe(6);
  expect(tabs().trees.research!.active_right).toBe("t-thread");
  expect(tabsSaved(tabs())).toBe(true);
});
