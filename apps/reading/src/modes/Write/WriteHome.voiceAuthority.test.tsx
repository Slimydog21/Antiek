import type { Editor, UseEditorOptions } from "@tiptap/react";
import type { DependencyList } from "react";
import { useEffect, useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import RequireAuth from "../../lib/RequireAuth";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import type { DeliverableDetailResponse } from "../../lib/api";
import { createInMemoryTabTreeAdapter } from "../../workspace/tabTree";
import { useTabTrees } from "../../workspace/tabTreeStore";
import { setTabOwner } from "../../workspace/tabTreeOwner";
import { setSectionProseOwner } from "./sectionProseOwner";

const { editors } = vi.hoisted(() => ({ editors: new Set<Editor>() }));
vi.mock("@tiptap/react", async (original) => {
  const actual = await original<typeof import("@tiptap/react")>();
  return {
    ...actual,
    useEditor(options: UseEditorOptions, deps?: DependencyList) {
      const editor = actual.useEditor(options, deps);
      if (editor) editors.add(editor);
      return editor;
    },
  };
});
// Auth, route, editor, voice capture and HTTP wrappers are real. Only the
// repository and recorder device seam are replaced, as in the review probe.
vi.mock("./BlockRepository", () => ({ default: () => null }));
import WriteHome from "./WriteHome";

const ORIGINAL = "Weak sentence. Second sentence.";
const rangeGeometry = {
  getBoundingClientRect: Object.getOwnPropertyDescriptor(Range.prototype, "getBoundingClientRect"),
  getClientRects: Object.getOwnPropertyDescriptor(Range.prototype, "getClientRects"),
};
type Reply = () => Promise<Response>;
let authReply: Reply;
let detailReply: Reply;
let patchReply: Reply;
let controller: AuthContextValue | null;
let detailRequests: number;
let mutations: string[];
let proseWrites: string[];
let enableWriting: () => void;

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});
const identity = (owner = "owner-a") => json({ user_id: owner, email: null, auth_method: "magic_link" });
function detail(prose = ORIGINAL): DeliverableDetailResponse {
  return {
    deliverable_id: "piece", title: "A piece", deliverable_kind: "general_essay", status: "draft", investigation_root_id: null,
    sections: [{ section_id: "section", deliverable_id: "piece", parent_section_id: null, section_index: 0, title: "Thesis", prose_text: prose, prose_provenance: {}, block_count: 0 }],
  };
}
function deferred() {
  let resolve: (response: Response) => void = () => { throw new Error("not initialized"); };
  const promise = new Promise<Response>((done) => { resolve = done; });
  return { promise, resolve };
}
function auth() {
  if (!controller) throw new Error("AuthProvider is not mounted");
  return controller;
}
function Probe() {
  const current = useAuth();
  const location = useLocation();
  useEffect(() => { controller = current; }, [current]);
  return <output data-testid="location">{location.pathname}</output>;
}
async function drain() {
  await act(async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); });
}
async function refresh(reply: Reply) {
  authReply = reply;
  await act(async () => { await auth().refresh(); });
}
function TestRoutes() {
  const [enabled, setEnabled] = useState(false);
  enableWriting = () => setEnabled(true);
  return <Routes><Route path="/login" element={<p>Login</p>} /><Route path="*" element={<RequireAuth><Routes><Route path="/write/:deliverableId" element={enabled ? <WriteHome /> : null} /></Routes></RequireAuth>} /></Routes>;
}
async function mount() {
  const view = render(<MemoryRouter initialEntries={["/write/piece"]}>
    <button>Outside focus</button>
    <AuthProvider><Probe /><TestRoutes /></AuthProvider>
  </MemoryRouter>);
  await waitFor(() => expect(controller?.state.status).toBe("authenticated"));
  await act(async () => { await useTabTrees.getState().bindActiveProject(async () => "project-a", () => createInMemoryTabTreeAdapter()); enableWriting(); });
  await screen.findByText("Thesis");
  await waitFor(() => expect(view.container.querySelector(".ProseMirror")).toBeTruthy());
  const editor = [...editors].find((candidate) => !candidate.isDestroyed);
  if (!editor) throw new Error("Real editor not mounted");
  await drain();
  return { ...view, editor, node: editor.view.dom };
}

beforeEach(() => {
  controller = null; editors.clear(); mutations = []; proseWrites = []; detailRequests = 0;
  setSectionProseOwner(null); setTabOwner(null); useTabTrees.getState().resetTabTrees();
  authReply = async () => identity();
  detailReply = async () => json(detail());
  patchReply = async () => json({ status: "saved" });
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }));
  Object.defineProperty(Range.prototype, "getBoundingClientRect", { configurable: true, value: () => new DOMRect() });
  Object.defineProperty(Range.prototype, "getClientRects", { configurable: true, value: () => ({ length: 0, item: () => null, [Symbol.iterator]: function* () {} }) });
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/health") return json({});
    if (path === "/auth/logout") return new Response(null, { status: 204 });
    if (path === "/deliverables/piece") { detailRequests++; return detailReply(); }
    if (path === "/write/sections/section/blocks") return json({ blocks: [] });
    if (init?.method && init.method !== "GET") mutations.push(path);
    if (path === "/sections/section/prose") {
      if (typeof init?.body !== "string") throw new Error("Missing prose body");
      const body: unknown = JSON.parse(init.body);
      if (!body || typeof body !== "object" || !("prose_text" in body) || typeof body.prose_text !== "string") throw new Error("Invalid prose body");
      proseWrites.push(body.prose_text);
      return patchReply();
    }
    if (path === "/events/typed") return json({});
    return json({ detail: "outside this controlled HTTP fixture" }, 404);
  }));
});
afterEach(() => {
  cleanup(); setSectionProseOwner(null); setTabOwner(null); useTabTrees.getState().resetTabTrees();
  for (const [method, descriptor] of Object.entries(rangeGeometry)) {
    if (descriptor) Object.defineProperty(Range.prototype, method, descriptor);
    else Reflect.deleteProperty(Range.prototype, method);
  }
  vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals();
});


const { recorderStub } = vi.hoisted(() => ({ recorderStub: {
  state: "recording", error: null, blob: { size: 24, type: "audio/webm" },
  getBlob: () => ({ size: 24, type: "audio/webm" }),
  start: vi.fn(async () => {}), stop: vi.fn(), reset: vi.fn(),
} }));
vi.mock("../../hooks/useVoiceRecorder", () => ({ useVoiceRecorder: () => recorderStub }));

it.each(["suspension", "omission", "owner"] as const)("blocks delayed voice persistence after %s", async (boundary) => {
  const { editor, node } = await mount();
  const transcribe = deferred();
  const originalFetch = vi.mocked(fetch).getMockImplementation();
  if (!originalFetch) throw new Error("Missing controlled HTTP fixture");
  const delayedWrites: { path: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/voice/transcribe") return transcribe.promise;
    if (path === "/events/typed" || path === "/write/blocks") {
      delayedWrites.push({ path, body: JSON.parse(String(init?.body)) });
      return json(path === "/events/typed" ? { event_id: "voice-event" } : { outline_block_id: "spoken-block" });
    }
    return originalFetch(input, init);
  });
  fireEvent.click(screen.getByRole("button", { name: /Speak an idea/ }));
  await screen.findByRole("button", { name: /Stop & add/ });
  fireEvent.click(screen.getByRole("button", { name: /Stop & add/ }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/voice/transcribe"))).toBe(true));
  expect(delayedWrites).toEqual([]);
  await refresh(async () => json({}, 503));
  if (boundary === "omission") {
    detailReply = async () => json({ ...detail(), sections: [] });
    await refresh(async () => identity());
    await drain();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    expect(node.isConnected).toBe(false);
    expect(editor.isDestroyed).toBe(true);
  } else if (boundary === "owner") {
    await refresh(async () => identity("replacement-owner"));
    await drain();
    expect(node.isConnected).toBe(false);
  } else {
    expect(node.closest("[hidden][inert]")).toBeTruthy();
  }
  await act(async () => { transcribe.resolve(json({ transcript: "Late spoken text", language: "en", duration_seconds: 1 })); });
  await drain();
  expect(delayedWrites).toEqual([]);
});

async function holdCapture(stage: "transcribe" | "event" | "block") {
  const held = deferred();
  const originalFetch = vi.mocked(fetch).getMockImplementation();
  if (!originalFetch) throw new Error("Missing controlled HTTP fixture");
  const writes: { path: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/voice/transcribe") return stage === "transcribe" ? held.promise : json({ transcript: "Spoken idea", language: "en", duration_seconds: 1 });
    if (path === "/events/typed" || path === "/write/blocks") {
      writes.push({ path, body: JSON.parse(String(init?.body)) });
      if ((stage === "event" && path === "/events/typed") || (stage === "block" && path === "/write/blocks")) return held.promise;
      return json(path === "/events/typed" ? { event_id: "voice-event" } : { outline_block_id: "spoken-block" });
    }
    return originalFetch(input, init);
  });
  fireEvent.click(screen.getByRole("button", { name: /Speak an idea/ }));
  await screen.findByRole("button", { name: /Stop & add/ });
  fireEvent.click(screen.getByRole("button", { name: /Stop & add/ }));
  const heldPath = stage === "transcribe" ? "/voice/transcribe" : stage === "event" ? "/events/typed" : "/write/blocks";
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith(heldPath))).toBe(true));
  return { held, writes };
}

async function revoke(boundary: "suspension" | "omission" | "logout" | "invalid" | "project") {
  if (boundary === "project") {
    await act(async () => { await useTabTrees.getState().bindActiveProject(async () => "project-b", () => createInMemoryTabTreeAdapter()); });
    return;
  }
  await refresh(async () => json({}, 503));
  if (boundary === "omission") {
    detailReply = async () => json({ ...detail(), sections: [] });
    await refresh(async () => identity()); await drain();
  }
  if (boundary === "logout") await act(async () => { await auth().signOut(); });
  if (boundary === "invalid") await refresh(async () => json({}, 401));
}

it.each(["logout", "invalid", "project"] as const)("blocks delayed voice persistence after proven %s", async (boundary) => {
  await mount(); const { held, writes } = await holdCapture("transcribe");
  expect(writes).toEqual([]);
  await revoke(boundary);
  await act(async () => { held.resolve(json({ transcript: "Old destination", language: "en", duration_seconds: 1 })); }); await drain();
  expect(writes).toEqual([]);
});

it.each(["suspension", "omission", "project"] as const)("an admitted capture acknowledgment cannot place into a section after %s", async (boundary) => {
  await mount(); const { held, writes } = await holdCapture("event");
  expect(writes.map((write) => write.path)).toEqual(["/events/typed"]);
  await revoke(boundary);
  await act(async () => { held.resolve(json({ event_id: "acknowledged-voice" })); }); await drain();
  expect(writes.map((write) => write.path)).toEqual(["/events/typed"]);
});

it("an admitted block acknowledgment cannot start old-context refreshes after suspension", async () => {
  await mount(); const { held, writes } = await holdCapture("block");
  expect(writes.map((write) => write.path)).toEqual(["/events/typed", "/write/blocks"]);
  await revoke("suspension");
  const reads = vi.mocked(fetch).mock.calls.length;
  await act(async () => { held.resolve(json({ outline_block_id: "acknowledged-block" })); }); await drain();
  expect(vi.mocked(fetch).mock.calls.length).toBe(reads);
  expect(writes.map((write) => write.path)).toEqual(["/events/typed", "/write/blocks"]);
});

it("a currently authorized section still captures and places actual user-sourced voice", async () => {
  await mount(); const { held, writes } = await holdCapture("transcribe");
  await act(async () => { held.resolve(json({ transcript: "Spoken idea", language: "en", duration_seconds: 1 })); }); await drain();
  expect(writes).toEqual([
    { path: "/events/typed", body: expect.objectContaining({ payload: expect.objectContaining({ action_type: "voice.captured", source_kind: "user", transcript: "Spoken idea" }) }) },
    { path: "/write/blocks", body: expect.objectContaining({ section_id: "section", deliverable_id: "piece", content: "Spoken idea", block_kind: "user_authored", provenance_kind: "user_authored" }) },
  ]);
  expect(screen.getByText(/Added.*your spoken draft/)).toBeTruthy();
});
