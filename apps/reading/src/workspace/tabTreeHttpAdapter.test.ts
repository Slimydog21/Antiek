/**
 * tabTreeHttpAdapter.test.ts — A2a items 4 and 5: the model's TabTreeAdapter
 * over lane B's wire module (GET/PUT/allocate/retired, THREAD-CONTRACT §1.6),
 * driven through the vendored projectTabs.ts with only `apiFetch` mocked, so
 * every body is parsed exactly as it will be in production.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "../lib/api/__fixtures__/projectTabs.snapshot.json";
import type { RetiredEntry, TabNode as WireNode, TabsSnapshot } from "../lib/api/projectTabs";
import {
  closeTab,
  fromSnapshot,
  restoreClosed,
  setActive,
  spawnChild,
  toSnapshot,
  undo,
  type TabTree,
  type TabTreeResult,
  type TabTreeSnapshot,
} from "./tabTree";
import { createHttpTabTreeAdapter } from "./tabTreeHttpAdapter";
import { fromWire } from "./tabTreeWire";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const expected = (): TabsSnapshot => clone(fixture.expected as unknown as TabsSnapshot);

function respond(status: number, body: unknown) {
  apiFetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => clone(body),
    text: async () => JSON.stringify(body),
  });
}

function sentBody(call: number): { tree: { nodes: Record<string, WireNode>; root_order: string[] }; active: unknown; expected_version: number } {
  const [, init] = apiFetchMock.mock.calls[call];
  return JSON.parse(init.body as string);
}

function treeOf(s: TabTreeSnapshot): TabTree {
  const r = fromSnapshot(s);
  if (!r.ok) throw new Error(r.error.message);
  return r.tree;
}

function must(r: TabTreeResult<{ tree: TabTree }>): TabTree {
  if (!r.ok) throw new Error(r.error.message);
  return r.tree;
}

/** A retired node that left by prune: the server set its pruned_at. */
const prunedEntry: RetiredEntry = {
  closed_at: "2026-09-27T00:00:01.000000Z",
  close_mode: "prune",
  node: {
    tab_id: "t-pruned",
    parent_tab_id: "t-doc",
    side: "left",
    kind: "reader",
    ref: "doc-fixture-3",
    title: "Weld inspection notes",
    mothership: "research",
    public_number: 5,
    hier_number: "2.1",
    child_order: [],
    pruned_at: "2026-09-27T00:00:01.000000Z",
  },
};

function withPruned(): TabsSnapshot {
  const s = expected();
  s.retired = [clone(prunedEntry), ...s.retired];
  s.next_child_index = { ...s.next_child_index, "t-doc": 2 };
  return s;
}

beforeEach(() => apiFetchMock.mockReset());
afterEach(() => vi.restoreAllMocks());

describe("createHttpTabTreeAdapter: load and save (contract §1.6)", () => {
  it("load GETs the tree and hands the model the fixture, retired[] as history", async () => {
    respond(200, expected());
    const adapter = createHttpTabTreeAdapter();
    const got = treeOf(await adapter.load("fld-1", "research"));
    expect(apiFetchMock.mock.calls[0][0]).toMatch(/\/projects\/fld-1\/tabs\/research$/);
    expect(got).toStrictEqual(fromWire(expected(), "research"));
    expect(Object.keys(got.history)).toEqual(["t-dialogue"]);
  });

  it("save PUTs the whole tree with expected_version and answers saved {snapshot} from the server", async () => {
    respond(200, expected());
    const adapter = createHttpTabTreeAdapter();
    let tree = treeOf(await adapter.load("fld-1", "research"));
    tree = must(spawnChild(tree, "t-doc", { tab_id: "t-new", kind: "reader", ref: "doc-9", mothership: "research" }));
    const server = expected();
    server.version = 3;
    server.tree.nodes["t-new"] = { ...clone(tree.nodes["t-new"]), public_number: 5 } as WireNode;
    server.tree.nodes["t-doc"].child_order = ["t-new"];
    server.tree.nodes["t-doc"].last_visited_child_id = "t-new";
    server.next_child_index = { ...server.next_child_index, "t-doc": 2 };
    server.active = { left: "t-new", right: "t-thread" };
    respond(200, server);
    const result = await adapter.save("fld-1", "research", toSnapshot(tree));
    const [url, init] = apiFetchMock.mock.calls[1];
    expect(url).toMatch(/\/projects\/fld-1\/tabs\/research$/);
    expect(init.method).toBe("PUT");
    const body = sentBody(1);
    expect(body.expected_version).toBe(2);
    expect(body.tree.nodes["t-new"].public_number).toBeNull();
    expect(Object.keys(body.tree.nodes)).not.toContain("t-dialogue");
    if (result.status !== "saved") throw new Error(result.status);
    const saved = treeOf(result.snapshot);
    expect(saved.version).toBe(3);
    expect(saved.nodes["t-new"].public_number).toBe(5);
    expect(Object.keys(saved.history)).toEqual(["t-dialogue"]);
  });

  it("both 409 reasons answer conflict {reason, current} for the rebase path", async () => {
    respond(200, expected());
    const adapter = createHttpTabTreeAdapter();
    const tree = treeOf(await adapter.load("fld-1", "research"));
    const newer = expected();
    newer.version = 7;
    respond(409, { reason: "version_stale", current: newer });
    const stale = await adapter.save("fld-1", "research", toSnapshot(tree));
    expect(stale.status === "conflict" && stale.reason).toBe("version_stale");
    if (stale.status === "conflict") expect(treeOf(stale.current).version).toBe(7);

    respond(409, { reason: "number_conflict", tab_id: "t-doc", detail: "belongs to another tab", current: newer });
    const clash = await adapter.save("fld-1", "research", toSnapshot(tree));
    if (clash.status !== "conflict") throw new Error(clash.status);
    expect(clash.reason).toBe("number_conflict");
    expect(clash.tab_id).toBe("t-doc");
    expect(treeOf(clash.current).version).toBe(7);
  });

  it("a 422 answers invalid {reason, tab_id, detail} and never throws", async () => {
    respond(200, expected());
    const adapter = createHttpTabTreeAdapter();
    const tree = treeOf(await adapter.load("fld-1", "research"));
    respond(422, { reason: "tab_origin_invalid", tab_id: "t-x", detail: "an agent-opened tab needs opened_by" });
    await expect(adapter.save("fld-1", "research", toSnapshot(tree))).resolves.toEqual({
      status: "invalid",
      reason: "tab_origin_invalid",
      tab_id: "t-x",
      detail: "an agent-opened tab needs opened_by",
    });
  });

  it("allocate posts the tab id; a retry after a lost response gets the same number", async () => {
    const adapter = createHttpTabTreeAdapter();
    respond(200, { public_number: 6 });
    respond(200, { public_number: 6 });
    expect(await adapter.allocate("fld-1", "writing", "t-new")).toEqual({ public_number: 6 });
    expect(await adapter.allocate("fld-1", "writing", "t-new")).toEqual({ public_number: 6 });
    for (const call of [0, 1]) {
      const [url, init] = apiFetchMock.mock.calls[call];
      expect(url).toMatch(/\/projects\/fld-1\/tabs\/writing\/allocate$/);
      expect(JSON.parse(init.body as string)).toEqual({ tab_id: "t-new" });
    }
  });

  it("older retirements page through GET …/retired until next_before is null", async () => {
    const adapter = createHttpTabTreeAdapter();
    respond(200, { retired: [clone(prunedEntry)], next_before: prunedEntry.closed_at });
    respond(200, { retired: [], next_before: null });
    const first = await adapter.retired!("fld-1", "research", null);
    expect(first.next_before).toBe(prunedEntry.closed_at);
    expect(first.entries.map((e) => [e.node.tab_id, e.close_mode, e.closed_at])).toEqual([
      ["t-pruned", "prune", prunedEntry.closed_at],
    ]);
    const second = await adapter.retired!("fld-1", "research", first.next_before);
    expect(second).toEqual({ entries: [], next_before: null });
    expect(apiFetchMock.mock.calls[1][0]).toContain(`/retired?before=${encodeURIComponent(prunedEntry.closed_at)}`);
  });

  it("the server's answer keeps the client's close ids, so an undo after the write still works", async () => {
    respond(200, expected());
    const adapter = createHttpTabTreeAdapter();
    const tree = treeOf(await adapter.load("fld-1", "research"));
    const closed = closeTab(tree, "t-doc", "prune", "2026-09-27T05:00:00Z");
    if (!closed.ok) throw new Error(closed.error.message);
    const server = expected();
    server.version = 3;
    delete (server.tree.nodes as Record<string, WireNode>)["t-doc"];
    server.tree.root_order = ["t-thread"];
    server.retired = [
      { closed_at: "2026-09-27T05:00:00.000001Z", close_mode: "close", node: clone(expected().tree.nodes["t-doc"]) },
      ...server.retired,
    ];
    respond(200, server);
    const result = await adapter.save("fld-1", "research", toSnapshot(closed.tree));
    if (result.status !== "saved") throw new Error(result.status);
    const adopted = treeOf(result.snapshot);
    expect(adopted.history["t-doc"].close_id).toBe(closed.undo.close_id);
    expect(adopted.history["t-doc"].closed_at).toBe("2026-09-27T05:00:00.000001Z");
    expect(undo(adopted, closed.undo).ok).toBe(true);
  });
});

describe("restore from history (contract §2.2 rev 8.8)", () => {
  it("the restore PUT sends the retired node back unchanged, pruned_at included", async () => {
    respond(200, withPruned());
    const adapter = createHttpTabTreeAdapter();
    const tree = treeOf(await adapter.load("fld-1", "research"));
    expect(tree.history["t-pruned"].node.pruned_at).toBe(prunedEntry.closed_at);
    const restored = must(restoreClosed(tree, "t-pruned"));
    respond(409, { reason: "version_stale", current: withPruned() }); // the body is what is under test
    await adapter.save("fld-1", "research", toSnapshot(restored));
    const sent = sentBody(1).tree.nodes["t-pruned"];
    expect(sent).toStrictEqual(prunedEntry.node);
  });

  it("never sends pruned_at on a tab it is not restoring, before or after the restore is accepted", async () => {
    respond(200, withPruned());
    const adapter = createHttpTabTreeAdapter();
    const tree = treeOf(await adapter.load("fld-1", "research"));
    // A plain write while a pruned retirement sits in history: no pruned_at anywhere.
    respond(409, { reason: "version_stale", current: withPruned() });
    await adapter.save("fld-1", "research", toSnapshot(must(setActive(tree, "t-doc"))));
    expect(JSON.stringify(sentBody(1))).not.toContain("pruned_at");

    // The restore is accepted: the server clears pruned_at and the tab is open.
    const restored = must(restoreClosed(tree, "t-pruned"));
    const accepted = withPruned();
    accepted.version = 3;
    accepted.retired = accepted.retired.filter((r) => r.node.tab_id !== "t-pruned");
    const reopened = clone(prunedEntry.node);
    delete reopened.pruned_at;
    accepted.tree.nodes["t-pruned"] = reopened;
    accepted.tree.nodes["t-doc"].child_order = ["t-pruned"];
    accepted.tree.nodes["t-doc"].last_visited_child_id = "t-pruned";
    respond(200, accepted);
    const result = await adapter.save("fld-1", "research", toSnapshot(restored));
    expect(sentBody(2).tree.nodes["t-pruned"].pruned_at).toBe(prunedEntry.closed_at);
    if (result.status !== "saved") throw new Error(result.status);

    // The next write of the adopted tree carries no pruned_at.
    respond(409, { reason: "version_stale", current: accepted });
    await adapter.save("fld-1", "research", toSnapshot(must(setActive(treeOf(result.snapshot), "t-doc"))));
    expect(JSON.stringify(sentBody(3))).not.toContain("pruned_at");

    // A stale local tree that still carries it on a tab the server holds open
    // is a lane-A bug: logged, and the field is not sent.
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    respond(409, { reason: "version_stale", current: accepted });
    await adapter.save("fld-1", "research", toSnapshot(restored));
    expect(sentBody(4).tree.nodes["t-pruned"].pruned_at).toBeUndefined();
    expect(error).toHaveBeenCalled();
  });
});
