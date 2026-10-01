import { useLayoutEffect } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ProjectSelector from "./ProjectSelector";
import CompanionPane from "./CompanionPane";
import { DocumentTabStrip } from "./DocumentTabStrip";
import { assignPublicNumber, emptyTabTree, setPaneActive, spawnChild } from "./tabTree";
import { toWireSnapshot } from "./tabTreeWire";
import { parseTabsSnapshot, type TabsSnapshot } from "../lib/api/projectTabs";
import { setTabOwner, suspendTabDispatch } from "./tabTreeOwner";
import { useTabTrees } from "./tabTreeStore";
import { useCompanion } from "./companionStore";
import { useProjectSelection } from "./projectSelection";

const tabs = () => useTabTrees.getState();
const comp = () => useCompanion.getState();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const project = (id: string) => ({ project_id: id, title: `Project ${id}`, kind: "project", order: 0, pinned: false, archived_at: null, primary_document_id: null, created_at: "2026-10-01", updated_at: null, member_count: 0 });
function fixture(id: string): TabsSnapshot {
  let tree = emptyTabTree("reading");
  for (const [tab_id, kind, ref, side, number] of [[`doc${id}`, "reader", `source${id}`, "left", 11], [`agent${id}`, "research", `thread${id}`, "right", 12]] as const) {
    const spawn = spawnChild(tree, null, { tab_id, kind, ref, side, title: `${kind} ${id}`, mothership: "reading", activate: side === "left" });
    if (!spawn.ok) throw new Error(spawn.error.message);
    const numbered = assignPublicNumber(spawn.tree, tab_id, number);
    if (!numbered.ok) throw new Error(numbered.error.message);
    tree = numbered.tree;
  }
  const active = setPaneActive(tree, "right", `agent${id}`);
  if (!active.ok) throw new Error(active.error.message);
  return toWireSnapshot(active.tree);
}
function Route() {
  const location = useLocation();
  const navigate = useNavigate();
  useLayoutEffect(() => { window.history.replaceState({ key: location.key }, "", location.pathname + location.search); }, [location]);
  return <><output data-testid="route">{location.pathname + location.search}</output><button type="button" onClick={() => navigate("/write")}>Writing mode door</button><button type="button" onClick={() => navigate("/library")}>Reading mode door</button></>;
}
function mount(path = "/library?project=B") {
  return render(<MemoryRouter initialEntries={[path]}><Route /><ProjectSelector /><DocumentTabStrip /><CompanionPane /></MemoryRouter>);
}
function server() {
  const rows = new Map<string, TabsSnapshot>([["A", fixture("A")], ["B", fixture("B")]]);
  const projects = [project("A"), project("B")];
  const allocations: string[] = [];
  const puts: { project: string; row: TabsSnapshot }[] = [];
  const statusReads: string[] = [];
  let holdA: Promise<void> | null = null;
  let holdProjects: Promise<void> | null = null;
  let listReply: (() => Response | Promise<Response>) | null = null;
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(String(input), window.location.origin).pathname.replace(/^\/api/, "");
    if (path === "/projects") {
      if (init?.method === "POST") {
        const created = { ...project("C"), title: JSON.parse(String(init.body)).title as string };
        projects.push(created);
        rows.set("C", toWireSnapshot(emptyTabTree("reading")));
        return json(created);
      }
      if (holdProjects) await holdProjects;
      return json({ projects });
    }
    if (path === "/investigations") return listReply ? listReply() : json({ count: 3, investigations: ["A", "B", "new"].map((id) => ({ investigation_id: `thread${id}`, question: `Question ${id}`, status: "completed", started_at: null, completed_at: null, cost_usd_total: 0, parent_investigation_id: null, document_id: `source${id}` })) });
    const statusMatch = /^\/investigations\/([^/]+)$/.exec(path);
    if (statusMatch) {
      const thread = decodeURIComponent(statusMatch[1]);
      statusReads.push(thread);
      return json({ investigation_id: thread, status: "completed" });
    }
    if (/\/tabs\/(writing|research)$/.test(path)) return json(toWireSnapshot(emptyTabTree(path.endsWith("writing") ? "writing" : "research")));
    const match = /^\/projects\/([^/]+)\/tabs\/reading(\/allocate)?$/.exec(path);
    if (!match) throw new Error(`Unexpected request ${path}`);
    const id = match[1];
    const old = rows.get(id);
    if (!old) return json({ detail: "Not found" }, 404);
    if (match[2]) { allocations.push(`${id}:${JSON.parse(String(init?.body)).tab_id}`); return json({ public_number: 100 + allocations.length }); }
    if (init?.method === "PUT") {
      const body: unknown = JSON.parse(String(init.body));
      if (!body || typeof body !== "object" || !("tree" in body) || !("active" in body) || !("expected_version" in body)) throw new Error("Bad PUT");
      expect(body.expected_version).toBe(old.version);
      const proposed = parseTabsSnapshot({ ...old, tree: body.tree, active: body.active, version: old.version + 1 });
      const counters = { ...old.next_child_index };
      for (const node of Object.values(proposed.tree.nodes)) {
        const parent = node.parent_tab_id ?? "root";
        const index = Number(node.hier_number.split(".").at(-1));
        counters[parent] = Math.max(counters[parent] ?? 1, index + 1);
      }
      const next = { ...proposed, next_child_index: counters };
      rows.set(id, next);
      puts.push({ project: id, row: next });
      return json(next);
    }
    if (id === "A" && holdA) await holdA;
    return json(old);
  });
  vi.stubGlobal("fetch", fetcher);
  return { rows, projects, puts, allocations, statusReads, fetcher, hold: (promise: Promise<void>) => { holdA = promise; }, holdRegistry: (promise: Promise<void>) => { holdProjects = promise; }, list: (reply: () => Response | Promise<Response>) => { listReply = reply; } };
}
beforeEach(() => { setTabOwner(null); setTabOwner("owner"); tabs().resetTabTrees(); comp().reset(); useProjectSelection.setState({ requestedId: null, status: "idle" }); });
afterEach(() => { cleanup(); setTabOwner(null); tabs().resetTabTrees(); comp().reset(); vi.unstubAllGlobals(); window.history.replaceState({}, "", "/"); });

it("restores the actual selected project's visible right agent and left document, switches, and reloads without copying", async () => {
  const backend = server();
  const mounted = mount();
  await waitFor(() => expect(screen.getByTestId("route").textContent).toBe("/read/sourceB?project=B"));
  expect(tabs().projectId).toBe("B");
  expect(screen.getByRole("tab", { name: /Question B/ }).getAttribute("aria-selected")).toBe("true");
  expect(tabs().trees.reading?.active_left).toBe("docB");
  expect(comp().activeTabId).toBe("agentB");
  expect(screen.getByText("Open research →").closest("a")?.getAttribute("href")).toBe("/inv/threadB?project=B&m=reading");
  expect(backend.puts).toHaveLength(0);
  fireEvent.change(screen.getByLabelText("Selected project"), { target: { value: "A" } });
  await waitFor(() => expect(comp().activeTabId).toBe("agentA"));
  await waitFor(() => expect(screen.getByTestId("route").textContent).toBe("/read/sourceA?project=A"));
  expect(screen.queryByRole("tab", { name: /Question B/ })).toBeNull();
  expect(tabs().trees.reading?.nodes.docB).toBeUndefined();
  mounted.unmount();
  act(() => { tabs().resetTabTrees(); comp().reset(); });
  mount("/read/sourceA?project=A");
  await waitFor(() => expect(comp().activeTabId).toBe("agentA"));
  expect(comp().tabs[0].publicNumber).toBe(12);
  expect(tabs().trees.reading?.active_left).toBe("docA");
  expect(backend.allocations).toEqual([]);
});

it("keeps the selected project through raw mode doors and restores that mode's right selection", async () => {
  server();
  mount();
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
  fireEvent.click(screen.getByText("Writing mode door"));
  await waitFor(() => expect(screen.getByTestId("route").textContent).toBe("/write?project=B"));
  expect(tabs().projectId).toBe("B");
  expect(tabs().trees.reading?.active_right).toBe("agentB");
  fireEvent.click(screen.getByText("Reading mode door"));
  await waitFor(() => expect(screen.getByTestId("route").textContent).toBe("/library?project=B"));
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
});

it("revalidates a still-mounted selection after an explicit tree context reset", async () => {
  const backend = server();
  mount();
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
  const calls = backend.fetcher.mock.calls.length;
  act(() => tabs().resetTabTrees());
  await waitFor(() => expect(tabs().projectId).toBe("B"));
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
  expect(backend.fetcher.mock.calls.slice(calls).some(([url]) => String(url).endsWith("/projects"))).toBe(true);
  expect(backend.allocations).toEqual([]);
});

it("reads the restored thread's real status after the first admitted project list fails", async () => {
  const backend = server();
  mount("/library?project=A");
  await screen.findByRole("tab", { name: /Question A/ });
  backend.list(() => json({ detail: "List unavailable" }, 503));
  fireEvent.change(screen.getByLabelText("Selected project"), { target: { value: "B" } });
  await waitFor(() => expect(useProjectSelection.getState().status).toBe("ready"));
  expect(tabs().projectId).toBe("B");
  await screen.findByText("done");
  expect(comp().activeTabId).toBe("agentB");
  expect(backend.statusReads).toEqual(["threadB"]);
  expect(screen.queryByText("Loading this thread’s status…")).toBeNull();
  expect(screen.queryByText("Question A")).toBeNull();
  expect(screen.queryByText("$0.00")).toBeNull();
  expect(screen.queryByText("Open source document →")).toBeNull();
  expect(screen.getByText("Open research →").closest("a")?.getAttribute("href")).toBe("/inv/threadB?project=B&m=reading");
  expect(backend.puts).toEqual([]);
  expect(backend.allocations).toEqual([]);
});

it("reads status for a restored older thread excluded from a successful list", async () => {
  const backend = server();
  backend.list(() => json({ count: 0, investigations: [] }));
  mount();
  await screen.findByText("done");
  expect(useProjectSelection.getState().status).toBe("ready");
  expect(backend.statusReads).toEqual(["threadB"]);
  expect(screen.queryByText("Question B")).toBeNull();
  expect(screen.queryByText("$0.00")).toBeNull();
  expect(screen.queryByText("Open source document →")).toBeNull();
});

it("does not read saved-reference status when a pending list fails during auth uncertainty", async () => {
  const backend = server();
  mount("/library?project=A");
  await screen.findByRole("tab", { name: /Question A/ });
  let reject = (_error: Error) => {};
  const pending = new Promise<Response>((_resolve, rejectRequest) => { reject = rejectRequest; });
  backend.list(() => pending);
  fireEvent.change(screen.getByLabelText("Selected project"), { target: { value: "B" } });
  await waitFor(() => expect(useProjectSelection.getState().status).toBe("ready"));
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
  await act(async () => { suspendTabDispatch(); reject(new Error("List unavailable")); });
  expect(tabs().trees.reading?.nodes.agentB).toBeDefined();
  expect(backend.statusReads).toEqual([]);
  act(() => setTabOwner("owner"));
  await screen.findByText("done");
  expect(backend.statusReads).toEqual(["threadB"]);
});

it("does not read a saved reference for an unresolved owner", async () => {
  const backend = server();
  backend.list(() => json({ count: 0, investigations: [] }));
  act(() => setTabOwner(null));
  mount();
  await waitFor(() => expect(useProjectSelection.getState().status).toBe("unavailable"));
  expect(tabs().projectId).toBeNull();
  expect(backend.statusReads).toEqual([]);
  expect(backend.fetcher.mock.calls.some(([url]) => String(url).includes("/tabs/"))).toBe(false);
});

it("does not read the previous owner's reference while the replacement project's admission is pending or denied", async () => {
  const backend = server();
  mount();
  await screen.findByRole("tab", { name: /Question B/ });
  let release = () => {};
  backend.holdRegistry(new Promise<void>((resolve) => { release = resolve; }));
  backend.projects.splice(1, 1);
  backend.list(() => json({ count: 0, investigations: [] }));
  act(() => setTabOwner("replacement"));
  await waitFor(() => expect(useProjectSelection.getState().status).toBe("loading"));
  expect(comp().tabs).toEqual([]);
  expect(tabs().projectId).toBeNull();
  expect(backend.statusReads).toEqual([]);
  await act(async () => { release(); });
  await screen.findByText("This project is unavailable for this account. Choose a project.");
  expect(backend.statusReads).toEqual([]);
});

it.each(["foreign", "invalid/project"])("does not request a saved-reference status for an unadmitted project %s", async (id) => {
  const backend = server();
  backend.list(() => json({ count: 0, investigations: [] }));
  mount(`/library?project=${encodeURIComponent(id)}`);
  await screen.findByText("This project is unavailable for this account. Choose a project.");
  expect(tabs().projectId).toBeNull();
  expect(backend.statusReads).toEqual([]);
  expect(backend.fetcher.mock.calls.some(([url]) => String(url).includes("/tabs/"))).toBe(false);
});

it("ignores an old project's late tab GET and retains a one-shot draft during selection", async () => {
  const backend = server();
  let release = () => {};
  backend.hold(new Promise<void>((resolve) => { release = resolve; }));
  mount("/library?project=A");
  await waitFor(() => expect(backend.fetcher.mock.calls.some(([url]) => String(url).includes("/A/tabs/reading"))).toBe(true));
  act(() => comp().openAgentTab({ kind: "dialogue" }));
  fireEvent.change(screen.getByLabelText("Ask the thought partner"), { target: { value: "Keep this entered prompt" } });
  fireEvent.change(screen.getByLabelText("Selected project"), { target: { value: "B" } });
  await waitFor(() => expect(tabs().projectId).toBe("B"));
  await act(async () => { release(); });
  await waitFor(() => expect(tabs().trees.reading?.nodes.agentB).toBeDefined());
  expect(tabs().trees.reading?.nodes.agentA).toBeUndefined();
  expect((screen.getByLabelText("Ask the thought partner") as HTMLTextAreaElement).value).toBe("Keep this entered prompt");
  expect(Object.values(backend.rows.get("B")!.tree.nodes).some((node) => node.kind === "dialogue")).toBe(false);
});

it("refuses another owner's unknown selection and accepts a real created project through the native selector", async () => {
  const backend = server();
  mount("/library?project=foreign");
  await screen.findByText("This project is unavailable for this account. Choose a project.");
  expect(tabs().projectId).toBeNull();
  expect(backend.fetcher.mock.calls.some(([url]) => String(url).includes("/foreign/tabs"))).toBe(false);
  fireEvent.click(screen.getByLabelText("Create project"));
  fireEvent.change(screen.getByLabelText("Project title"), { target: { value: "My new project" } });
  fireEvent.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => expect(tabs().projectId).toBe("C"));
  expect(screen.getByTestId("route").textContent).toBe("/library?project=C");
  expect(backend.rows.get("C")?.tree.nodes).toEqual({});
});

it("opens a real research reference and its source document in the selected row with exact provenance", async () => {
  const backend = server();
  mount();
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
  fireEvent.click(screen.getByLabelText("New agent"));
  fireEvent.click(await screen.findByRole("menuitem", { name: /Question new/ }));
  await waitFor(() => expect(comp().tabs.find((tab) => tab.investigationId === "threadnew")?.publicNumber).toBe(101));
  const agent = comp().tabs.find((tab) => tab.investigationId === "threadnew")!;
  expect(agent.id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  expect(backend.rows.get("B")?.active.right).toBe(agent.id);
  expect(tabs().trees.reading?.active_left).toBe("docB");
  fireEvent.click(screen.getByText("Open source document →"));
  await waitFor(() => expect(backend.puts.some(({ row }) => Object.values(row.tree.nodes).some((node) => node.kind === "reader" && node.ref === "sourcenew"))).toBe(true));
  const opened = Object.values(backend.rows.get("B")!.tree.nodes).find((node) => node.kind === "reader" && node.ref === "sourcenew")!;
  expect(opened.side).toBe("left");
  expect(opened.branch_origin?.kind).toBe("agent");
  expect(opened.opened_by).toEqual({ thread_id: "threadnew", agent_kind: "research" });
  expect(opened.public_number).toBe(102);
  expect(backend.rows.get("A")?.tree.nodes[opened.tab_id]).toBeUndefined();
  expect(backend.allocations).toEqual([`B:${agent.id}`, `B:${opened.tab_id}`]);
});

it("clears the old owner's visible agent and one-shot draft before validating that owner's URL for a replacement account", async () => {
  const backend = server();
  mount();
  await waitFor(() => expect(comp().activeTabId).toBe("agentB"));
  act(() => { comp().openAgentTab({ kind: "dialogue" }); comp().setDialogue({ prompt: "Private old-owner draft" }); });
  const fetcher = backend.fetcher;
  fetcher.mockImplementation(async (input) => {
    if (String(input).includes("/projects")) return json({ projects: [project("A")] });
    return json({ count: 0, investigations: [] });
  });
  act(() => setTabOwner("replacement"));
  expect(comp().tabs).toEqual([]);
  expect(comp().dialogue.prompt).toBe("");
  expect(screen.queryByText("Private old-owner draft")).toBeNull();
  await screen.findByText("This project is unavailable for this account. Choose a project.");
  expect(tabs().projectId).toBeNull();
  expect(tabs().trees.reading).toBeNull();
});
