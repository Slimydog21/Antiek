import type { Editor, UseEditorOptions } from "@tiptap/react";
import type { DependencyList } from "react";
import { useEffect, useState } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import RequireAuth from "../../lib/RequireAuth";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import type { DeliverableDetailResponse } from "../../lib/api";
import { createInMemoryTabTreeAdapter } from "../../workspace/tabTree";
import { useTabTrees } from "../../workspace/tabTreeStore";
import { setTabOwner, suspendTabDispatch } from "../../workspace/tabTreeOwner";
import { setSectionProseOwner, suspendSectionProseDispatch } from "./sectionProseOwner";
import { sectionProse } from "./sectionProse";

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
// Only the unrelated repository UI is replaced. Auth, route protection,
// detail reads, Outline, WriteEditor, TipTap/history and both stores are real.
vi.mock("./BlockRepository", () => ({ default: () => null }));
import WriteHome from "./WriteHome";
import { runInlineComplete } from "./Editor/InlineComplete";

const ORIGINAL = "Weak sentence. Second sentence.";
const EDITED = "Sharper sentence. Second sentence.";
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
async function edit(editor: Editor) {
  await act(async () => {
    const tr = editor.state.tr.setNodeMarkup(0, undefined, { ...editor.state.doc.firstChild?.attrs, blockId: "block-fixture" });
    tr.addMark(16, editor.state.doc.content.size - 1, editor.schema.marks.bold.create());
    editor.view.dispatch(tr.setMeta("addToHistory", false));
  });
  await act(async () => {
    editor.view.dispatch(editor.state.tr.insertText("Sharper sentence.", 1, 15));
    editor.commands.setTextSelection({ from: 3, to: 8 });
    editor.view.dom.focus();
  });
  expect(editor.getText()).toBe(EDITED);
  expect(editor.getJSON().content?.[0]?.attrs?.blockId).toBe("block-fixture");
  await act(async () => { editor.commands.undo(); });
  expect(editor.getText()).toBe(ORIGINAL);
  await act(async () => { editor.commands.redo(); editor.commands.setTextSelection({ from: 3, to: 8 }); editor.view.dom.focus(); });
  expect(editor.getText()).toBe(EDITED);
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

it.each(["unavailable", "inferred"] as const)("retains real undo, document, selection and focus through %s auth and fresh detail", async (kind) => {
  const { editor, node, container } = await mount();
  await edit(editor);
  const document = editor.getJSON();
  const selection = editor.state.selection;
  mutations = [];
  await refresh(kind === "unavailable" ? async () => json({}, 503) : async () => { throw new TypeError("Failed to fetch"); });
  // Longer than useEditor's scheduled destruction after unmount.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
  expect(editor.isDestroyed).toBe(false);
  expect(container.querySelector(".ProseMirror")).toBe(node);
  expect(node.closest("[hidden][inert]")).toBeTruthy();
  expect(editor.isEditable).toBe(false);
  expect(screen.getByTestId("location").textContent).toBe("/write/piece");
  const complete = vi.fn().mockResolvedValue({ text: "blocked" });
  await act(async () => { await runInlineComplete(editor, { pending: false }, complete); });
  expect(complete).not.toHaveBeenCalled();
  expect(mutations).toEqual([]);
  vi.useFakeTimers();
  await act(async () => { await vi.advanceTimersByTimeAsync(1200); });
  expect(mutations).toEqual([]);
  vi.useRealTimers();
  const fresh = deferred(); detailReply = () => fresh.promise;
  await refresh(async () => identity());
  await drain();
  expect(detailRequests).toBe(2);
  expect(node.closest("[hidden][inert]")).toBeTruthy();
  expect(mutations).toEqual([]);
  await act(async () => { fresh.resolve(json(detail("Stale server prose."))); });
  await drain();
  expect(container.querySelector(".ProseMirror")).toBe(node);
  expect(editor.getJSON()).toEqual(document);
  expect(editor.state.selection.eq(selection)).toBe(true);
  expect(globalThis.document.activeElement).toBe(node);
  expect(editor.isEditable).toBe(true);
  await act(async () => { editor.commands.undo(); });
  expect(editor.getText()).toBe(ORIGINAL);
  await act(async () => { editor.commands.redo(); });
  expect(editor.getText()).toBe(EDITED);
});

it.each(["unavailable", "inferred"] as const)("initial %s identity never mounts the protected editor", async (kind) => {
  authReply = kind === "unavailable" ? async () => json({}, 503) : async () => { throw new TypeError("Failed to fetch"); };
  const { container } = render(<MemoryRouter initialEntries={["/write/piece"]}><AuthProvider><Probe /><TestRoutes /></AuthProvider></MemoryRouter>);
  if (kind === "unavailable") await screen.findByText("Antiek can't reach its server right now.");
  else await screen.findByText("Login");
  expect(container.querySelector(".ProseMirror")).toBeNull();
  expect(editors.size).toBe(0);
  expect(detailRequests).toBe(0);
});

it("stale identity and detail replies cannot expose or overwrite the retained real editor", async () => {
  const { editor, node } = await mount(); await edit(editor);
  const savedDocument = editor.getJSON();
  const session = sectionProse("piece", "section", ORIGINAL, {});
  const staleIdentity = deferred(); authReply = () => staleIdentity.promise;
  let oldRefresh = Promise.resolve(); act(() => { oldRefresh = auth().refresh(); });
  await refresh(async () => json({}, 503));
  await act(async () => { staleIdentity.resolve(identity()); await oldRefresh; });
  expect(node.closest("[hidden][inert]")).toBeTruthy();
  const obsoleteDetail = deferred(); detailReply = () => obsoleteDetail.promise;
  await refresh(async () => identity()); await drain();
  expect(detailRequests).toBe(2);
  await refresh(async () => json({}, 503));
  const latestDetail = deferred(); detailReply = () => latestDetail.promise;
  await refresh(async () => identity()); await drain();
  expect(detailRequests).toBe(3);
  // Obsolete membership must not revoke the current retained section.
  await act(async () => { obsoleteDetail.resolve(json({ ...detail(), sections: [] })); }); await drain();
  expect(session.getSnapshot().available).toBe(true);
  expect(node.isConnected).toBe(true);
  expect(node.closest("[hidden][inert]")).toBeTruthy();
  expect(editor.getJSON()).toEqual(savedDocument);
  await act(async () => { latestDetail.resolve(json(detail())); }); await drain();
  expect(node.closest("[hidden][inert]")).toBeNull();
  expect(editor.getJSON()).toEqual(savedDocument);
  await act(async () => { editor.commands.undo(); }); expect(editor.getText()).toBe(ORIGINAL);
});

it("a fresh authoritative detail refusal destroys the retained editing session", async () => {
  const { editor, node } = await mount(); await edit(editor);
  await refresh(async () => json({}, 503));
  detailReply = async () => json({}, 403);
  await refresh(async () => identity()); await drain();
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
  expect(editor.isDestroyed).toBe(true);
  expect(node.isConnected).toBe(false);
  expect(screen.queryByText("Sharper sentence. Second sentence.")).toBeNull();
});

it("fresh detail omission revokes a retained section and its queued writes before the same ID returns", async () => {
  const { editor, node } = await mount(); vi.useFakeTimers(); await edit(editor);
  const session = sectionProse("piece", "section", ORIGINAL, {});
  const admittedPatch = deferred(); patchReply = () => admittedPatch.promise;
  await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  expect(proseWrites).toEqual([EDITED]);
  await act(async () => { editor.view.dispatch(editor.state.tr.insertText("Queued removed section.", 1, editor.state.doc.content.size - 1)); });
  await refresh(async () => json({}, 503));
  const fresh = deferred(); detailReply = () => fresh.promise;
  await refresh(async () => identity()); await drain();
  expect(detailRequests).toBe(2);
  expect(session.getSnapshot().available).toBe(true);
  expect(session.getSnapshot().dispatchAllowed).toBe(false);
  expect(proseWrites).toEqual([EDITED]);
  mutations = [];
  await act(async () => { fresh.resolve(json({ ...detail(), sections: [] })); }); await drain();
  expect(session.getSnapshot().available).toBe(false);
  expect(session.getSnapshot().document).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(30); });
  expect(editor.isDestroyed).toBe(true);
  expect(node.isConnected).toBe(false);
  expect(mutations).toEqual([]);
  await act(async () => { admittedPatch.resolve(json({ status: "saved" })); await vi.advanceTimersByTimeAsync(1200); });
  expect(proseWrites).toEqual([EDITED]);
  expect(mutations).toEqual([]);
  // A later accepted response can contain the same ID. It must start a new
  // session from that response, never resurrect or flush the removed draft.
  await refresh(async () => json({}, 503));
  detailReply = async () => json(detail("Fresh returned section."));
  await refresh(async () => identity()); await drain();
  const next = [...editors].find((candidate) => candidate !== editor && !candidate.isDestroyed);
  expect(next?.getText()).toBe("Fresh returned section.");
  await act(async () => { next?.commands.undo(); await vi.advanceTimersByTimeAsync(1200); });
  expect(next?.getText()).toBe("Fresh returned section.");
  expect(proseWrites).toEqual([EDITED]);
});

it("session revocation blocks actual capture before React disposes the old editor", async () => {
  const { editor } = await mount(); await edit(editor);
  expect(mutations).toContain("/events/typed"); mutations = [];
  const session = sectionProse("piece", "section", ORIGINAL, {});
  act(() => {
    session.dispose();
    // Revocation precedes React's editability effect/unmount. Exercise an
    // already-held real instance during that gap, with owner/project valid.
    expect(editor.isEditable).toBe(true);
    editor.view.dispatch(editor.state.tr.insertText("Late removed section.", 1, editor.state.doc.content.size - 1));
  });
  expect(mutations).toEqual([]);
  expect(session.getSnapshot().draft).toBeNull();
});

it("direct editor transactions cannot emit granular capture during suspension", async () => {
  const { editor } = await mount(); await edit(editor);
  expect(mutations).toContain("/events/typed");
  await refresh(async () => json({}, 503)); mutations = [];
  // Exercise onUpdate directly as an adverse stale completion, rather than
  // trusting inert alone to block a callback already holding the instance.
  await act(async () => { editor.view.dispatch(editor.state.tr.insertText("Late", 1, 5)); });
  expect(mutations).toEqual([]);
});

it("a revoked project's admitted PATCH cannot dispatch a queued follow-up or seed the new project's editor", async () => {
  const { editor } = await mount(); vi.useFakeTimers(); await edit(editor);
  const oldPatch = deferred(); patchReply = () => oldPatch.promise;
  await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  expect(proseWrites).toEqual([EDITED]);
  await act(async () => { editor.view.dispatch(editor.state.tr.insertText("Queued old project.", 1, editor.state.doc.content.size - 1)); });
  detailReply = async () => json(detail("Fresh project prose."));
  await act(async () => { await useTabTrees.getState().bindActiveProject(async () => "project-b", () => createInMemoryTabTreeAdapter()); });
  await drain();
  const next = [...editors].find((candidate) => candidate !== editor && !candidate.isDestroyed);
  expect(next?.getText()).toBe("Fresh project prose.");
  await act(async () => { oldPatch.resolve(json({ status: "saved" })); await vi.advanceTimersByTimeAsync(1200); });
  expect(proseWrites).toEqual([EDITED]);
  expect(next?.getText()).toBe("Fresh project prose.");
});

it("a mounted detail suspension preserves the same editor without stealing later focus", async () => {
  const { editor, node } = await mount(); await edit(editor);
  const before = detailRequests;
  await act(async () => { suspendSectionProseDispatch(); suspendTabDispatch(); });
  await drain();
  expect(node.isConnected).toBe(true);
  expect(editor.isDestroyed).toBe(false);
  expect(node.closest("[hidden][inert]")).toBeTruthy();
  const outside = screen.getByRole("button", { name: "Outside focus" }); outside.focus();
  const fresh = deferred(); detailReply = () => fresh.promise;
  await act(async () => { setSectionProseOwner("owner-a"); setTabOwner("owner-a"); });
  await drain(); expect(detailRequests).toBe(before + 1);
  await act(async () => { fresh.resolve(json(detail())); }); await drain();
  expect(globalThis.document.activeElement).toBe(outside);
  await act(async () => { editor.commands.undo(); }); expect(editor.getText()).toBe(ORIGINAL);
});

it("a batched suspend/resume still requires a fresh detail read and retains the original history", async () => {
  const { editor, node } = await mount(); await edit(editor);
  const fresh = deferred(); detailReply = () => fresh.promise;
  await act(async () => {
    suspendSectionProseDispatch(); suspendTabDispatch();
    setSectionProseOwner("owner-a"); setTabOwner("owner-a");
  });
  await drain();
  expect(detailRequests).toBe(2);
  expect(node.closest("[hidden][inert]")).toBeTruthy();
  expect(proseWrites).toEqual([]);
  await act(async () => { fresh.resolve(json(detail())); }); await drain();
  expect(node.closest("[hidden][inert]")).toBeNull();
  await act(async () => { editor.commands.undo(); }); expect(editor.getText()).toBe(ORIGINAL);
});

it.each(["owner", "logout", "invalid", "project"] as const)("destroys the prior editor on a proven %s boundary", async (kind) => {
  const { editor, node } = await mount(); await edit(editor);
  detailReply = async () => json(detail("Fresh authorized prose."));
  if (kind === "owner") {
    await refresh(async () => identity("owner-b"));
    await act(async () => { await useTabTrees.getState().bindActiveProject(async () => "project-a", () => createInMemoryTabTreeAdapter()); enableWriting(); });
  }
  if (kind === "invalid") await refresh(async () => json({}, 401));
  if (kind === "logout") await act(async () => { await auth().signOut(); });
  if (kind === "project") await act(async () => {
    await useTabTrees.getState().bindActiveProject(async () => "project-b", () => createInMemoryTabTreeAdapter());
  });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
  expect(editor.isDestroyed).toBe(true);
  expect(node.isConnected).toBe(false);
  if (kind === "owner" || kind === "project") {
    await waitFor(() => expect([...editors].some((candidate) => !candidate.isDestroyed && candidate.getText() === "Fresh authorized prose.")).toBe(true));
    const next = [...editors].find((candidate) => !candidate.isDestroyed);
    expect(next).toBeTruthy();
    await act(async () => { next?.commands.undo(); });
    expect(next?.getText()).not.toContain("Sharper sentence.");
  }
});
