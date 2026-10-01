import { useEffect, useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import RequireAuth from "../../lib/RequireAuth";
import { createInMemoryTabTreeAdapter } from "../../workspace/tabTree";
import { useTabTrees } from "../../workspace/tabTreeStore";
import { setTabOwner, suspendTabDispatch } from "../../workspace/tabTreeOwner";
import WriteHome from "./WriteHome";

type Reply = () => Promise<Response>;
let authReply: Reply;
let createReply: Reply;
let promoteReply: Reply;
let startReply: Reply;
let controller: AuthContextValue | null;
let enable: () => void;
let disable: () => void;
let move: (path: string) => void;
let listReply: Reply;
let writes: { path: string; body: unknown }[];
const tabs = () => useTabTrees.getState();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});
const identity = (owner = "owner-a") => json({ user_id: owner, email: null, auth_method: "magic_link" });
const created = () => json({
  deliverable_id: "new-piece", title: "My piece", deliverable_kind: "general_essay",
  investigation_root_id: null, status: "draft", section_count: 0, created_at: null, updated_at: null,
});
function held() {
  let resolve: (response: Response) => void = () => { throw new Error("Uninitialized response"); };
  const promise = new Promise<Response>((done) => { resolve = done; });
  return { promise, resolve };
}
function Probe() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => { controller = auth; }, [auth]);
  useEffect(() => { move = navigate; }, [navigate]);
  return <output data-testid="location">{location.pathname + location.search}</output>;
}
function TestRoutes() {
  const [enabled, setEnabled] = useState(false);
  enable = () => setEnabled(true);
  disable = () => setEnabled(false);
  return <Routes>
    <Route path="/login" element={<p>Login</p>} />
    <Route path="*" element={<RequireAuth><Routes>
      <Route path="/write" element={enabled ? <WriteHome /> : null} />
      <Route path="/write/:deliverableId" element={<p>Created piece</p>} />
    </Routes></RequireAuth>} />
  </Routes>;
}
async function mount(query = "") {
  render(<MemoryRouter initialEntries={[`/write?project=project-a${query}`]}>
    <AuthProvider><Probe /><TestRoutes /></AuthProvider>
  </MemoryRouter>);
  await waitFor(() => expect(controller?.state.status).toBe("authenticated"));
  await act(async () => {
    await tabs().bindActiveProject(async () => "project-a", () => createInMemoryTabTreeAdapter());
    enable();
  });
  return screen.findByPlaceholderText(/what are you writing/i);
}
async function refresh(reply: Reply) {
  authReply = reply;
  if (!controller) throw new Error("Auth not mounted");
  await act(async () => { await controller?.refresh(); });
}
const emptyButton = () => screen.getByRole("button", { name: /start empty|start without a project/i });

beforeEach(() => {
  controller = null; writes = [];
  setTabOwner(null); tabs().resetTabTrees();
  authReply = async () => identity();
  createReply = async () => created();
  promoteReply = async () => json({ detail: "no_synthesis" }, 404);
  startReply = async () => json({ investigation_id: "new-research", status: "in_progress", start_event_id: "start-event" });
  listReply = async () => json({ investigations: [{
    investigation_id: "notebook-research", question: "What compounds?", status: "completed", spawned_by_daemon: true,
  }], count: 1 });
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }));
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/health") return json({});
    if (path === "/auth/logout") return new Response(null, { status: 204 });
    if (init?.method === "POST") {
      if (typeof init.body !== "string") throw new Error("Missing mutation body");
      const body: unknown = JSON.parse(init.body);
      writes.push({ path, body });
      if (path === "/deliverables") return createReply();
      if (path === "/write/deliverables/from-investigation") return promoteReply();
      if (path === "/investigations") return startReply();
    }
    if (path === "/deliverables") return json({ deliverables: [], count: 0 });
    if (path === "/investigations") return listReply();
    if (path === "/settings/models") return json({ models: [], count: 0, stale_registered: [] });
    return json({ detail: "outside this fixture" }, 404);
  }));
});
afterEach(() => { cleanup(); setTabOwner(null); tabs().resetTabTrees(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("empty creation reaches the actual deliverable transport without starting or promoting research", async () => {
  const title = await mount();
  fireEvent.change(title, { target: { value: "  A margins memo  " } });
  fireEvent.click(screen.getByRole("button", { name: "Research memo" }));
  fireEvent.click(emptyButton());
  await screen.findByText("Created piece");
  expect(writes.map((write) => write.path)).toEqual(["/deliverables"]);
  expect(writes[0].body).toEqual({ title: "A margins memo", deliverable_kind: "research_memo" });
  expect(screen.getByTestId("location").textContent).toBe("/write/new-piece?project=project-a");
});

it.each([409, 503])("an empty creation HTTP %s retains the form and permits an explicit retry", async (status) => {
  createReply = async () => json({ detail: "creation unavailable" }, status);
  const title = await mount();
  fireEvent.change(title, { target: { value: "Kept chapter" } });
  fireEvent.click(screen.getByRole("button", { name: "Book chapter" }));
  fireEvent.click(emptyButton());
  await screen.findByText(/couldn't create the piece/i);
  expect(title).toHaveProperty("value", "Kept chapter");
  expect(screen.getByTestId("location").textContent).toBe("/write?project=project-a");
  expect(writes).toEqual([{ path: "/deliverables", body: { title: "Kept chapter", deliverable_kind: "book_chapter" } }]);
  createReply = async () => created();
  fireEvent.click(emptyButton());
  await screen.findByText("Created piece");
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
});

it("a lost creation reply reports uncertainty without retrying or clearing the form", async () => {
  createReply = async () => { throw new Error("connection lost"); };
  const title = await mount();
  fireEvent.change(title, { target: { value: "Unconfirmed piece" } });
  fireEvent.click(emptyButton());
  await screen.findByText(/couldn't confirm whether the piece was created/i);
  expect(title).toHaveProperty("value", "Unconfirmed piece");
  expect(writes.map((write) => write.path)).toEqual(["/deliverables"]);
  expect(screen.queryByText("Created piece")).toBeNull();
});

it("an incoming notebook handoff replaces the creation intent and revokes old navigation", async () => {
  const request = held(); createReply = () => request.promise;
  const title = await mount();
  fireEvent.change(title, { target: { value: "Previous idea" } });
  fireEvent.click(emptyButton());
  await act(async () => { move("/write?project=project-a&investigation=notebook-research&title=Notebook%20idea"); });
  const destination = screen.getByTestId("location").textContent;
  await act(async () => { request.resolve(json({ deliverable_id: "previous-piece" })); });
  expect(screen.getByTestId("location").textContent).toBe(destination);
  expect(screen.getByRole("textbox", { name: "Piece title" })).toHaveProperty("value", "Notebook idea");
  expect(writes).toHaveLength(1);
});

it("a held empty-create request admits one write across duplicate presses", async () => {
  const request = held(); createReply = () => request.promise;
  const title = await mount();
  fireEvent.change(title, { target: { value: "One piece" } });
  const button = emptyButton();
  await act(async () => { fireEvent.click(button); fireEvent.click(button); fireEvent.click(button); });
  expect(writes).toHaveLength(1);
  expect(title.hasAttribute("disabled")).toBe(true);
  await act(async () => { request.resolve(created()); });
  await screen.findByText("Created piece");
  expect(writes).toHaveLength(1);
});

it("a stale empty action cannot dispatch across a batched suspend and resume before React updates", async () => {
  const title = await mount();
  fireEvent.change(title, { target: { value: "Live admission" } });
  const oldButton = emptyButton();
  await act(async () => {
    suspendTabDispatch();
    setTabOwner("owner-a");
    fireEvent.click(oldButton);
  });
  expect(writes).toEqual([]);
  fireEvent.click(emptyButton());
  await screen.findByText("Created piece");
  expect(writes.map((write) => write.path)).toEqual(["/deliverables"]);
});

async function changeScope(boundary: "suspension" | "owner" | "project" | "logout" | "invalid" | "unmount") {
  if (boundary === "suspension") {
    await refresh(async () => json({ detail: "temporary outage" }, 503));
    await refresh(async () => identity());
  } else if (boundary === "owner") {
    await refresh(async () => identity("owner-b"));
  } else if (boundary === "project") {
    await act(async () => {
      await tabs().bindActiveProject(async () => "project-b", () => createInMemoryTabTreeAdapter());
      move("/write?project=project-b");
    });
  } else if (boundary === "logout") {
    if (!controller) throw new Error("Auth not mounted");
    await act(async () => { await controller?.signOut(); });
  } else if (boundary === "invalid") {
    await refresh(async () => json({ detail: "revoked" }, 401));
  } else {
    await act(async () => { disable(); });
  }
}

it.each(["suspension", "owner", "project", "logout", "invalid", "unmount"] as const)(
  "an admitted empty-create acknowledgment cannot navigate after %s", async (boundary) => {
    const request = held(); createReply = () => request.promise;
    const title = await mount();
    fireEvent.change(title, { target: { value: "Old scope" } });
    fireEvent.click(emptyButton());
    expect(writes).toHaveLength(1);
    await changeScope(boundary);
    const before = screen.getByTestId("location").textContent;
    await act(async () => { request.resolve(created()); });
    expect(screen.getByTestId("location").textContent).toBe(before);
    expect(screen.queryByText("Created piece")).toBeNull();
    expect(writes).toHaveLength(1);
    if (boundary === "suspension") {
      await screen.findByText(/your piece was created/i);
      fireEvent.click(emptyButton());
      expect(writes).toHaveLength(1);
      fireEvent.click(screen.getByRole("button", { name: "Open your piece" }));
      await screen.findByText("Created piece");
    } else {
      expect(screen.queryByText(/your piece was created/i)).toBeNull();
    }
  },
);

it.each(["suspension", "owner", "project", "logout", "invalid"] as const)(
  "a held research-import 404 cannot dispatch an empty linked fallback after %s", async (boundary) => {
    const request = held(); promoteReply = () => request.promise;
    const title = await mount();
    fireEvent.change(title, { target: { value: "Research piece" } });
    fireEvent.click(await screen.findByRole("button", { name: /what compounds/i }));
    expect(writes.map((write) => write.path)).toEqual(["/write/deliverables/from-investigation"]);
    await changeScope(boundary);
    await act(async () => { request.resolve(json({ detail: "no_synthesis" }, 404)); });
    expect(writes.map((write) => write.path)).toEqual(["/write/deliverables/from-investigation"]);
    expect(screen.queryByText("Created piece")).toBeNull();
  },
);

it("existing autonomous notebook research still imports its outline without starting research", async () => {
  promoteReply = async () => json({ deliverable_id: "new-piece", block_count: 2 });
  await mount("&investigation=notebook-research&title=Notebook%20memo");
  await screen.findByTestId("connect-research-preferred");
  fireEvent.click(screen.getByRole("button", { name: /what compounds/i }));
  await screen.findByText("Created piece");
  expect(writes).toEqual([{ path: "/write/deliverables/from-investigation", body: {
    investigation_id: "notebook-research", title: "Notebook memo", deliverable_kind: "general_essay",
  } }]);
});

it("an authorized research choice without an outline still creates an explicitly linked piece", async () => {
  const title = await mount();
  fireEvent.change(title, { target: { value: "Linked piece" } });
  fireEvent.click(await screen.findByRole("button", { name: /what compounds/i }));
  await screen.findByText("Created piece");
  expect(writes.map((write) => write.path)).toEqual(["/write/deliverables/from-investigation", "/deliverables"]);
  expect(writes[1].body).toEqual({ title: "Linked piece", deliverable_kind: "general_essay", investigation_root_id: "notebook-research" });
});

it("failed research listing does not block a no-research piece", async () => {
  listReply = async () => json({ detail: "list unavailable" }, 503);
  const title = await mount();
  fireEvent.change(title, { target: { value: "Unlinked piece" } });
  await screen.findByText(/couldn't load your research projects/i);
  fireEvent.click(emptyButton());
  await screen.findByText("Created piece");
  expect(writes.map((write) => write.path)).toEqual(["/deliverables"]);
});

it("retrying piece creation reuses the already-started research instead of spending again", async () => {
  createReply = async () => json({ detail: "unavailable" }, 503);
  const title = await mount();
  fireEvent.change(title, { target: { value: "Explicit research" } });
  fireEvent.click(screen.getByRole("button", { name: /start research first/i }));
  await screen.findByText(/couldn't create the piece/i);
  expect(writes.map((write) => write.path)).toEqual(["/investigations", "/write/deliverables/from-investigation", "/deliverables"]);
  createReply = async () => created();
  fireEvent.click(screen.getByRole("button", { name: /create piece with started research/i }));
  await screen.findByText("Created piece");
  expect(writes.filter((write) => write.path === "/investigations")).toHaveLength(1);
  expect(writes.filter((write) => write.path === "/deliverables")).toHaveLength(2);
});

it.each(["suspension", "owner", "project"] as const)(
  "a research launch acknowledgment cannot create a piece after %s", async (boundary) => {
    const request = held(); startReply = () => request.promise;
    const title = await mount();
    fireEvent.change(title, { target: { value: "Explicit launch" } });
    fireEvent.click(screen.getByRole("button", { name: /start research first/i }));
    expect(writes.map((write) => write.path)).toEqual(["/investigations"]);
    await changeScope(boundary);
    await act(async () => { request.resolve(json({ investigation_id: "admitted-research", status: "in_progress", start_event_id: "admitted-event" })); });
    expect(writes.map((write) => write.path)).toEqual(["/investigations"]);
    expect(screen.queryByText("Created piece")).toBeNull();
    if (boundary === "suspension") expect(screen.getByRole("button", { name: /create piece with started research/i })).toBeTruthy();
  },
);
