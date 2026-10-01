import { act, cleanup, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth, type AuthContextValue } from "./auth";
import { useTabTrees, tabsSaved } from "../workspace/tabTreeStore";
import { setTabOwner } from "../workspace/tabTreeOwner";
import { parseTabsSnapshot, type TabsSnapshot } from "./api/projectTabs";
function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }); }
function identity(owner: string) { return json({ user_id: owner, email: null, auth_method: "magic_link" }); }
function deferred() { let resolve!: (value: Response) => void; const promise = new Promise<Response>((done) => { resolve = done; }); return { promise, resolve }; }
let controller: AuthContextValue | null;
let authReply: () => Promise<Response>;
let putGate: Promise<Response> | null;
let logoutGate: Promise<Response> | null;
let row: TabsSnapshot;
const requests: { path: string; method: string; signal: AbortSignal | null | undefined }[] = [];
let allocations: Map<string, number>;
const tabs = () => useTabTrees.getState();
function auth() { if (!controller) throw new Error("not mounted"); return controller; }
function Consumer() {
  const value = useAuth();
  useEffect(() => { controller = value; }, [value]);
  return <output>{value.state.status}</output>;
}
async function drain() { await act(async () => { for (let i = 0; i < 80; i++) await Promise.resolve(); }); }
function spawn(id: string) { tabs().spawnTab("reading", null, { tab_id: id, kind: "reader", ref: id, mothership: "reading" }); }
const writes = () => requests.filter((r) => r.method === "PUT");
const allocates = () => requests.filter((r) => r.path.endsWith("/allocate"));
async function mount() {
  render(<AuthProvider><Consumer /></AuthProvider>);
  await screen.findByText("authenticated");
  await tabs().bindActiveProject();
  await tabs().ensureMothership("reading");
}
async function refresh(reply: () => Promise<Response>) { authReply = reply; await act(async () => { await auth().refresh(); }); }
beforeEach(() => {
  setTabOwner(null); tabs().resetTabTrees(); controller = null;
  putGate = null; logoutGate = null; requests.length = 0; allocations = new Map();
  row = { tree: { nodes: {}, root_order: [] }, active: { left: null, right: null }, version: 0, next_child_index: {}, retired: [] };
  authReply = async () => identity("owner-A");
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init?.method ?? "GET"; requests.push({ path, method, signal: init?.signal });
    if (path === "/auth/me") return authReply();
    if (path === "/health") return json({});
    if (path === "/auth/logout") return logoutGate ?? json({});
    if (path === "/projects") return json({ projects: [{ project_id: "project-A", title: "Project", kind: "project", order: 0, pinned: false, archived_at: null, primary_document_id: null, created_at: "2026-09-27", updated_at: null, member_count: 0 }] });
    if (path.endsWith("/allocate")) {
      const body: unknown = JSON.parse(String(init?.body));
      if (!body || typeof body !== "object" || !("tab_id" in body) || typeof body.tab_id !== "string") throw new Error("bad allocate body");
      if (!allocations.has(body.tab_id)) allocations.set(body.tab_id, allocations.size + 1);
      return json({ public_number: allocations.get(body.tab_id) });
    }
    if (path === "/projects/project-A/tabs/reading") {
      if (method === "GET") return json(row);
      if (method === "PUT") {
        const body: unknown = JSON.parse(String(init?.body));
        if (!body || typeof body !== "object" || !("tree" in body) || !("active" in body) || !("expected_version" in body)) throw new Error("bad PUT body");
        expect(body.expected_version).toBe(row.version);
        row = parseTabsSnapshot({ ...row, tree: body.tree, active: body.active, version: row.version + 1 });
        row.next_child_index = { root: Math.max(0, ...Object.values(row.tree.nodes).map((node) => Number(node.hier_number))) + 1 };
        return putGate ?? json(row);
      }
    }
    throw new Error(`Unexpected ${method} ${path}`);
  }));
});
afterEach(() => { act(() => { setTabOwner(null); }); cleanup(); tabs().resetTabTrees(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("AuthProvider and HTTP tab persistence", () => {
  it.each(["unavailable", "inferred"] as const)("%s suspends new HTTP work, retains pending tabs and resumes on same owner", async (kind) => {
    await mount();
    const gate = deferred(); putGate = gate.promise;
    spawn("first"); await drain(); expect(writes()).toHaveLength(1);
    await refresh(kind === "unavailable" ? async () => json({}, 503) : async () => { throw new TypeError("network"); });
    expect(writes()[0].signal?.aborted).toBe(true);
    spawn("pending"); putGate = null; gate.resolve(json(row)); await drain();
    expect(writes()).toHaveLength(1); expect(allocates()).toHaveLength(1);
    expect(tabs().trees.reading!.nodes.pending).toBeTruthy(); expect(tabsSaved(tabs())).toBe(false);
    await refresh(async () => identity("owner-A")); await drain();
    expect(writes()).toHaveLength(2); expect(allocates()).toHaveLength(2); expect(tabsSaved(tabs())).toBe(true);
  });
  it("confirmed A to B transition prevents old queued HTTP follow-up", async () => {
    await mount(); const gate = deferred(); putGate = gate.promise;
    spawn("first"); await drain(); spawn("oldPending");
    await refresh(async () => identity("owner-B")); gate.resolve(json(row)); await drain();
    expect(writes()).toHaveLength(1); expect(allocates()).toHaveLength(1);
    expect(tabs().trees.reading).toBeNull(); expect(tabs().projectId).toBeNull();
  });
  it("logout revokes queued work before its HTTP response and stale refresh cannot reactivate it", async () => {
    await mount(); const gate = deferred(); putGate = gate.promise;
    spawn("first"); await drain(); spawn("oldPending");
    const stale = deferred(); authReply = () => stale.promise; let refreshing!: Promise<void>;
    act(() => { refreshing = auth().refresh(); });
    const logout = deferred(); logoutGate = logout.promise; let signingOut!: Promise<void>;
    act(() => { signingOut = auth().signOut(); });
    expect(tabs().trees.reading).toBeNull();
    expect(writes()[0].signal?.aborted).toBe(true);
    stale.resolve(identity("owner-A")); gate.resolve(json(row));
    await act(async () => { await refreshing; }); await drain();
    expect(writes()).toHaveLength(1); expect(allocates()).toHaveLength(1);
    expect(tabs().trees.reading).toBeNull();
    logout.resolve(json({})); await act(async () => { await signingOut; });
  });
});
