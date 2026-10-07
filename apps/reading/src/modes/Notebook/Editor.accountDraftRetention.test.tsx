import { createRef, useEffect, useState } from "react";
import type { Editor as TipTapEditor } from "@tiptap/react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import { beforeWorkspaceOwnerChange, isWorkspaceOwnerSession, notebookDraftKey, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import * as draftStorage from "../../lib/notebookDraftStorage";
import { toast } from "../../components/lemon/LemonToast";
import { NotebookEditor } from "./Editor";

// Actual auth, storage and TipTap lifetimes run. Only HTTP is synthetic.
const notebookId = "captured-local-draft";
const accountA = "acct_local_draft_a";
const accountB = "acct_local_draft_b";
let controller: AuthContextValue | null;
let identityReply: () => Promise<Response>;
let notebookReply: () => Promise<Response>;
let putReply: () => Promise<Response>;
const fetches = vi.fn<typeof fetch>();
const disposers: Array<() => void> = [];

function response(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function identity(subject = accountA): Response {
  return response(200, { user_id: subject, email: null, auth_method: "magic_link" });
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("Deferred reply not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
function auth(): AuthContextValue {
  if (controller === null) throw new Error("Actual auth consumer has not mounted");
  return controller;
}
function localKey(): string {
  const key = notebookDraftKey(notebookId);
  if (key === null) throw new Error("A verified notebook owner is required");
  return key;
}
function putCalls() {
  return fetches.mock.calls.filter(([, init]) => init?.method === "PUT");
}
function mountNotebook(startOpen = true, delay = { ms: 60000 }) {
  const editorRef = createRef<TipTapEditor>();
  function View() {
    const current = useAuth();
    const [open, setOpen] = useState(startOpen);
    useEffect(() => { controller = current; }, [current]);
    return <>
      <output data-testid="draft-identity">{current.state.status === "authenticated" ? current.state.identity.user_id : current.state.status}</output>
      {current.state.status === "authenticated" && (open
        ? <NotebookEditor notebookId={notebookId} editorRef={editorRef} autosaveDelayMs={delay.ms} />
        : <button onClick={() => setOpen(true)}>Open notebook</button>)}
    </>;
  }
  const mounted = render(<MemoryRouter><AuthProvider><View /></AuthProvider></MemoryRouter>);
  return { ...mounted, editorRef };
}
async function hydrated(mounted: ReturnType<typeof mountNotebook>): Promise<TipTapEditor> {
  try {
    await waitFor(() => {
      expect(mounted.container.querySelector("[data-notebook-editor]")?.getAttribute("data-hydrated")).toBe("true");
      expect(mounted.editorRef.current).not.toBeNull();
    });
  } catch (error) {
    throw new Error(JSON.stringify({
      subject: workspaceOwnerSession().subject,
      ready: isWorkspaceOwnerSession(workspaceOwnerSession()),
      cachedBytes: localStorage.getItem(notebookDraftKey(notebookId) ?? "")?.length ?? null,
      editorDestroyed: mounted.editorRef.current?.isDestroyed ?? null,
      identityReads: fetches.mock.calls.filter(([input]) => String(input).endsWith("/auth/me")).length,
      notebookReads: fetches.mock.calls.filter(([input, init]) => String(input).endsWith("/content") && init?.method !== "PUT").length,
    }), { cause: error });
  }
  const editor = mounted.editorRef.current;
  if (editor === null) throw new Error("Actual notebook editor did not hydrate");
  return editor;
}
function edit(editor: TipTapEditor, text: string): string {
  act(() => { editor.commands.setContent(`<p>${text}</p>`); });
  return editor.getHTML();
}

beforeEach(() => {
  setWorkspaceOwner(null);
  localStorage.clear();
  sessionStorage.clear();
  controller = null;
  identityReply = async () => identity();
  notebookReply = async () => response(200, { notebook_id: notebookId, doc: { type: "doc", content: [] } });
  putReply = async () => response(200);
  fetches.mockReset().mockImplementation(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return identityReply();
    if (path === "/auth/logout") return new Response(null, { status: 204 });
    if (path === "/health") return response(200, { status: "ok" });
    if (path === `/notebooks/${notebookId}/content`) {
      return init?.method === "PUT" ? putReply() : notebookReply();
    }
    throw new Error(`Unexpected notebook lifetime request: ${path}`);
  });
  vi.stubGlobal("fetch", fetches);
});
afterEach(() => {
  vi.restoreAllMocks();
  for (const dispose of disposers.splice(0)) dispose();
  cleanup();
  setWorkspaceOwner(null);
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("captured pending notebook edits", () => {
  it("flushes A locally before logout, denies B restore and restores only a genuinely confirmed A", async () => {
    const mounted = mountNotebook();
    const editor = await hydrated(mounted);
    const owner = workspaceOwnerSession();
    const key = localKey();
    const html = edit(editor, "Pending A before autosave");
    expect(localStorage.getItem(key)).toBeNull();
    await act(async () => { await auth().signOut(); });
    expect(localStorage.getItem(key)).toBe(html);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    await waitFor(() => { expect(editor.isDestroyed).toBe(true); });
    expect(putCalls()).toHaveLength(0);

    identityReply = async () => identity(accountB);
    await act(async () => { await auth().refresh({ afterSignIn: true }); });
    const b = await hydrated(mounted);
    expect(screen.getByTestId("draft-identity").textContent).toBe(accountB);
    expect(b.getHTML()).not.toContain("Pending A");
    expect(localStorage.getItem(localKey())).toBeNull();
    await act(async () => { await auth().signOut(); });

    identityReply = async () => identity();
    await act(async () => { await auth().refresh({ afterSignIn: true }); });
    const restored = await hydrated(mounted);
    expect(restored).not.toBe(editor);
    expect(restored.getHTML()).toBe(html);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(putCalls()).toHaveLength(0);
  });

  it("keeps authorized edits through actual suspension, server-unavailable unmount and same-A Retry", async () => {
    const mounted = mountNotebook();
    const editor = await hydrated(mounted);
    const owner = workspaceOwnerSession();
    const key = localKey();
    const html = edit(editor, "A edit survives unavailable unmount");
    const reply = deferred<Response>();
    identityReply = () => reply.promise;
    let pending = Promise.resolve();
    act(() => { pending = auth().refresh(); });
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(mounted.editorRef.current).toBe(editor);
    await act(async () => { reply.resolve(response(503)); await pending; });
    expect(screen.getByRole("alert").getAttribute("data-auth-unavailable")).toBe("server");
    await waitFor(() => { expect(editor.isDestroyed).toBe(true); });
    expect(mounted.editorRef.current).toBeNull();
    expect(localStorage.getItem(key)).toBe(html);
    expect(putCalls()).toHaveLength(0);

    identityReply = async () => identity();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    const restored = await hydrated(mounted);
    expect(restored.getHTML()).toBe(html);
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(true);
    expect(putCalls()).toHaveLength(0);
  });

  it("retains pending edits even when an earlier retirement callback fails, without an outbound save", async () => {
    const primary = new Error("Earlier local retirement failed");
    const mounted = mountNotebook(false);
    await screen.findByText(accountA);
    disposers.push(beforeWorkspaceOwnerChange(() => { throw primary; }));
    fireEvent.click(screen.getByRole("button", { name: "Open notebook" }));
    const editor = await hydrated(mounted);
    const key = localKey();
    const html = edit(editor, "A edit despite another cleanup failure");
    await act(async () => { await expect(auth().signOut()).rejects.toBe(primary); });
    expect(localStorage.getItem(key)).toBe(html);
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(false);
    expect(screen.getByRole("alert").textContent).toContain("local cleanup");
    expect(putCalls()).toHaveLength(0);
  });

  it("reports a real local-storage refusal, closes the writer and still attempts cookie retirement", async () => {
    const mounted = mountNotebook();
    const editor = await hydrated(mounted);
    const key = localKey();
    edit(editor, "A edit whose local write is refused");
    const failure = new DOMException("Synthetic quota refusal", "QuotaExceededError");
    const original = Storage.prototype.setItem;
    const storage = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, name, value) {
      if (name === key) throw failure;
      return original.call(this, name, value);
    });
    await act(async () => { await expect(auth().signOut()).rejects.toBe(failure); });
    expect(storage.mock.calls.filter(([name]) => name === key)).toHaveLength(1);
    expect(localStorage.getItem(key)).toBeNull();
    expect(fetches.mock.calls.filter(([input]) => String(input).endsWith("/auth/logout"))).toHaveLength(1);
    expect(screen.queryByText("saved to local")).toBeNull();
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(false);
    expect(putCalls()).toHaveLength(0);
  });
});

describe("mounted notebook retention boundaries", () => {
  it("refuses a disposed editor's late PUT mirror after same-A recovery, preserving the new pending draft", async () => {
    const delayedPut = deferred<Response>();
    putReply = () => delayedPut.promise;
    const delay = { ms: 0 };
    const mounted = mountNotebook(true, delay);
    const old = await hydrated(mounted);
    const owner = workspaceOwnerSession();
    const key = localKey();
    const first = edit(old, "First editor dispatched edit");
    await waitFor(() => { expect(putCalls()).toHaveLength(1); });
    identityReply = async () => response(503);
    await act(async () => { await auth().refresh(); });
    await waitFor(() => { expect(old.isDestroyed).toBe(true); });
    expect(localStorage.getItem(key)).toBe(first);
    expect(localStorage.getItem(key + ".etag")).toBe("1");
    delay.ms = 60000;
    identityReply = async () => identity();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    const current = await hydrated(mounted);
    expect(workspaceOwnerSession()).toBe(owner);
    const second = edit(current, "Current editor pending edit must survive");
    await act(async () => { delayedPut.resolve(response(200)); await delayedPut.promise; });
    expect(localStorage.getItem(key + ".etag")).toBe("1");
    mounted.unmount();
    expect(localStorage.getItem(key)).toBe(second);
    expect(localStorage.getItem(key + ".etag")).toBe("2");
    expect(putCalls()).toHaveLength(1);
  });

  it("keeps the actual editor and pending draft through successful same-owner refresh", async () => {
    const mounted = mountNotebook();
    const editor = await hydrated(mounted);
    const owner = workspaceOwnerSession();
    const key = localKey();
    const html = edit(editor, "Same-A unsaved draft");
    const reply = deferred<Response>();
    identityReply = () => reply.promise;
    let pending = Promise.resolve();
    act(() => { pending = auth().refresh(); });
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    await act(async () => { reply.resolve(identity()); await pending; });
    expect(mounted.editorRef.current).toBe(editor);
    expect(workspaceOwnerSession()).toBe(owner);
    expect(editor.getHTML()).toBe(html);
    mounted.unmount();
    await waitFor(() => { expect(editor.isDestroyed).toBe(true); });
    expect(localStorage.getItem(key)).toBe(html);
    expect(putCalls()).toHaveLength(0);
  });

  it("flushes A on confirmed replacement and cannot let a disposed A editor write into B", async () => {
    const mounted = mountNotebook();
    const editor = await hydrated(mounted);
    const owner = workspaceOwnerSession();
    const key = localKey();
    const html = edit(editor, "A draft before confirmed B");
    identityReply = async () => identity(accountB);
    await act(async () => { await auth().refresh(); });
    const b = await hydrated(mounted);
    expect(localStorage.getItem(key)).toBe(html);
    expect(b.getHTML()).not.toContain("A draft");
    await waitFor(() => { expect(editor.isDestroyed).toBe(true); });
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(() => editor.commands.setContent("<p>Disposed A callback</p>")).toThrow(TypeError);
    expect(localStorage.getItem(key)).toBe(html);
    expect(localStorage.getItem(localKey())).toBeNull();
    expect(putCalls()).toHaveLength(0);
  });

  it("preserves a newer local revision instead of overwriting it at retirement", async () => {
    const mounted = mountNotebook();
    const editor = await hydrated(mounted);
    const key = localKey();
    edit(editor, "Older pending edit");
    expect(draftStorage.writeNotebookDraft(notebookId, "<p>Newer tab revision</p>", 0, workspaceOwnerSession())).toBe(1);
    const warning = vi.spyOn(toast, "err");
    await act(async () => { await auth().signOut(); });
    expect(localStorage.getItem(key)).toBe("<p>Newer tab revision</p>");
    expect(localStorage.getItem(key + ".etag")).toBe("1");
    expect(warning).toHaveBeenCalledWith(expect.stringContaining("Notebook conflict"));
    expect(putCalls()).toHaveLength(0);
  });

  it("does not retain an unhydrated command over a real read-only hydration failure", async () => {
    notebookReply = async () => response(503);
    const mounted = mountNotebook();
    await screen.findByText(/editing is paused/);
    const editor = mounted.editorRef.current;
    if (editor === null) throw new Error("Read-only editor did not mount");
    const key = localKey();
    expect(editor.isEditable).toBe(false);
    act(() => { editor.commands.setContent("<p>Unhydrated command must not become a draft</p>"); });
    await act(async () => { await auth().signOut(); });
    expect(localStorage.getItem(key)).toBeNull();
    expect(putCalls()).toHaveLength(0);
  });
});

// These controls exercise the producer/storage contract independently of React.
// Synthetic unit subjects are not live credential or account-creation proof.
describe("one-use local notebook writer", () => {
  beforeEach(() => { setWorkspaceOwner(accountA); });
  function capture() {
    const writer = draftStorage.captureNotebookDraft(notebookId, workspaceOwnerSession());
    if (writer === null) throw new Error("Ready unit producer could not capture its draft");
    return writer;
  }

  it("refuses anonymous, reconstructed and suspended producer identities", () => {
    const owner = workspaceOwnerSession();
    expect(draftStorage.captureNotebookDraft(notebookId, { ...owner })).toBeNull();
    suspendWorkspaceOwner();
    expect(draftStorage.captureNotebookDraft(notebookId, owner)).toBeNull();
    setWorkspaceOwner(null);
    expect(draftStorage.captureNotebookDraft(notebookId, workspaceOwnerSession())).toBeNull();
  });

  it("retains only previously authorized edits while suspension continues to deny read and outbound admission", () => {
    const owner = workspaceOwnerSession();
    const key = localKey();
    const writer = capture();
    expect(writer.record("<p>Authorized A snapshot</p>")).toBe(true);
    suspendWorkspaceOwner();
    expect(writer.record("<p>Unconfirmed injected edit</p>")).toBe(false);
    expect(writer.finish(0)).toEqual({ kind: "written", etag: 1 });
    expect(localStorage.getItem(key)).toBe("<p>Authorized A snapshot</p>");
    expect(draftStorage.readNotebookDraft(notebookId, owner)).toBeNull();
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    resumeWorkspaceOwner(owner);
    expect(writer.record("<p>Late reused writer</p>")).toBe(false);
    expect(writer.finish(1)).toEqual({ kind: "closed" });
    expect(draftStorage.readNotebookDraft(notebookId, owner)?.html).toBe("<p>Authorized A snapshot</p>");
  });

  it("refuses replacement and ABA even when the original subject returns", () => {
    const writer = capture();
    writer.record("<p>Stale A epoch</p>");
    setWorkspaceOwner(accountB);
    expect(draftStorage.readNotebookDraft(notebookId)).toBeNull();
    setWorkspaceOwner(accountA);
    const key = localKey();
    expect(draftStorage.writeNotebookDraft(notebookId, "<p>Current A revision</p>", 0, workspaceOwnerSession())).toBe(1);
    expect(writer.record("<p>Late stale callback</p>")).toBe(false);
    expect(writer.finish(1)).toEqual({ kind: "refused" });
    expect(writer.finish(1)).toEqual({ kind: "closed" });
    expect(localStorage.getItem(key)).toBe("<p>Current A revision</p>");
  });

  it("consumes etag refusal without permitting a later overwrite of the newer draft", () => {
    const key = localKey();
    const writer = capture();
    writer.record("<p>Old recorded edit</p>");
    draftStorage.writeNotebookDraft(notebookId, "<p>Newer revision</p>", 0, workspaceOwnerSession());
    expect(writer.finish(0)).toEqual({ kind: "conflict" });
    expect(writer.record("<p>Late attempt</p>")).toBe(false);
    expect(writer.finish(1)).toEqual({ kind: "closed" });
    expect(localStorage.getItem(key)).toBe("<p>Newer revision</p>");
  });

  it.each(["body", "etag"])("keeps the actual %s write error and retires the writer before a retry", (field) => {
    const key = localKey();
    const writer = capture();
    writer.record("<p>Pending local write</p>");
    const failure = new DOMException("Synthetic storage failure", "QuotaExceededError");
    const original = Storage.prototype.setItem;
    const storage = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, name, value) {
      if (name === (field === "body" ? key : key + ".etag")) throw failure;
      return original.call(this, name, value);
    });
    expect(writer.finish(0)).toEqual({ kind: "failed", error: failure });
    const attempts = storage.mock.calls.length;
    expect(writer.record("<p>Late error retry</p>")).toBe(false);
    expect(writer.finish(0)).toEqual({ kind: "closed" });
    expect(storage.mock.calls).toHaveLength(attempts);
    expect(localStorage.getItem(key + ".etag")).toBeNull();
  });

  it("closes before storage callbacks can re-enter or substitute a later body", () => {
    const key = localKey();
    const writer = capture();
    writer.record("<p>Original authorized snapshot</p>");
    const original = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, name, value) {
      if (name === key) {
        expect(writer.record("<p>Reentrant substitute</p>")).toBe(false);
        expect(writer.finish(0)).toEqual({ kind: "closed" });
      }
      return original.call(this, name, value);
    });
    expect(writer.finish(0)).toEqual({ kind: "written", etag: 1 });
    expect(localStorage.getItem(key)).toBe("<p>Original authorized snapshot</p>");
  });

  it("does not advance an already mirrored draft's etag on final close", () => {
    const writer = capture();
    writer.record("<p>Already mirrored</p>");
    draftStorage.writeNotebookDraft(notebookId, "<p>Already mirrored</p>", 0, workspaceOwnerSession());
    expect(writer.finish(1)).toEqual({ kind: "unchanged" });
    expect(localStorage.getItem(localKey() + ".etag")).toBe("1");
  });
});
