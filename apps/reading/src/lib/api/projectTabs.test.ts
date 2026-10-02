import { beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "./__fixtures__/projectTabs.snapshot.json";
import {
  allocateTab,
  getRetired,
  getTabs,
  parseTabsSnapshot,
  putTabs,
  type TabsSnapshot,
} from "./projectTabs";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../api", async (orig) => {
  const actual = await orig<typeof import("../api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

/** The fixture's expected GET answer, as the server sends it (closed_at included). */
const snapshot = fixture.expected as unknown as TabsSnapshot;

function respond(status: number, body: unknown) {
  apiFetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
}

beforeEach(() => apiFetchMock.mockReset());

describe("projectTabs wire module", () => {
  it("parses the shared fixture: both sides, an agent-opened tab, a retired node", async () => {
    respond(200, snapshot);
    const got = await getTabs("fld-1", "research");
    expect(apiFetchMock.mock.calls[0][0]).toMatch(/\/projects\/fld-1\/tabs\/research$/);
    expect(got.version).toBe(2);
    expect(got.active).toEqual({ left: "t-agent-doc", right: "t-thread" });
    const agentTab = got.tree.nodes["t-agent-doc"];
    expect(agentTab.side).toBe("left");
    expect(agentTab.branch_origin?.kind).toBe("agent");
    expect(agentTab.opened_by).toEqual({ thread_id: "inv-fixture-1", agent_kind: "research" });
    expect(got.tree.nodes["t-thread"].side).toBe("right");
    expect(got.retired.map((r) => [r.close_mode, r.node.tab_id])).toEqual([["close", "t-dialogue"]]);
    expect(got.next_child_index).toEqual({ root: 4, "t-thread": 2 });
  });

  it("refuses a malformed snapshot instead of half-parsing it", () => {
    expect(() => parseTabsSnapshot({ ...snapshot, version: -1 })).toThrow(/malformed/);
    const keyedWrong = { ...snapshot, tree: { ...snapshot.tree, nodes: { other: snapshot.tree.nodes["t-doc"] } } };
    expect(() => parseTabsSnapshot(keyedWrong)).toThrow(/malformed/);
  });

  it("a saved PUT answers the new snapshot, sent with expected_version", async () => {
    respond(200, snapshot);
    const body = { tree: snapshot.tree, active: snapshot.active, expected_version: 1 };
    const result = await putTabs("fld-1", "research", body);
    expect(result).toEqual({ status: "saved", snapshot });
    const [, init] = apiFetchMock.mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it("narrows both 409 reasons without string parsing, each with current", async () => {
    respond(409, { reason: "version_stale", current: snapshot });
    const stale = await putTabs("fld-1", "research", { tree: snapshot.tree, active: snapshot.active, expected_version: 0 });
    expect(stale.status === "conflict" && stale.conflict.reason).toBe("version_stale");

    respond(409, { reason: "number_conflict", tab_id: "t-doc", detail: "belongs to another tab", current: snapshot });
    const clash = await putTabs("fld-1", "research", { tree: snapshot.tree, active: snapshot.active, expected_version: 2 });
    if (clash.status !== "conflict" || clash.conflict.reason !== "number_conflict") throw new Error("not narrowed");
    expect(clash.conflict.tab_id).toBe("t-doc");
    expect(clash.conflict.current.version).toBe(2);
  });

  it("a 422 is an invalid result for lane A to log, never an operator error", async () => {
    respond(422, { reason: "tab_origin_invalid", tab_id: "t-x", detail: "an agent-opened tab needs opened_by" });
    const result = await putTabs("fld-1", "research", { tree: snapshot.tree, active: snapshot.active, expected_version: 2 });
    expect(result).toEqual({
      status: "invalid",
      invalid: { reason: "tab_origin_invalid", tab_id: "t-x", detail: "an agent-opened tab needs opened_by" },
    });
  });

  it("any other failure throws with its status", async () => {
    respond(404, { detail: "project_not_found" });
    await expect(getTabs("fld-x", "research")).rejects.toMatchObject({ status: 404 });
    respond(409, { detail: "something else" });
    await expect(
      putTabs("fld-1", "research", { tree: snapshot.tree, active: snapshot.active, expected_version: 0 }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("allocate posts the tab id and returns its number", async () => {
    respond(200, { public_number: 5 });
    await expect(allocateTab("fld-1", "writing", "t-new")).resolves.toEqual({ public_number: 5 });
    const [url, init] = apiFetchMock.mock.calls[0];
    expect(url).toMatch(/\/projects\/fld-1\/tabs\/writing\/allocate$/);
    expect(JSON.parse(init.body as string)).toEqual({ tab_id: "t-new" });
  });

  it("pages retirements with before and limit", async () => {
    respond(200, { retired: snapshot.retired, next_before: null });
    const page = await getRetired("fld-1", "research", { before: "2026-09-27T00:00:00.000000Z", limit: 50 });
    expect(page.next_before).toBeNull();
    expect(apiFetchMock.mock.calls[0][0]).toContain("/retired?before=2026-09-27T00%3A00%3A00.000000Z&limit=50");
  });
});
