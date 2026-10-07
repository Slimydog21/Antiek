import { useEffect, useState } from "react";
import { act, cleanup, fireEvent, isInaccessible, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BookDetail, FullTextResponse } from "../api/books";
import { AuthProvider, claimLogin, useAuth, type AuthContextValue } from "./auth";
import { beforeWorkspaceOwnerChange, isWorkspaceOwnerSession, notebookDraftKey, setWorkspaceOwner, workspaceOwnerSession } from "./accountWorkspaceOwner";
import { clearReadingFocus, formatReadingFocusSystemContext } from "./readingFocus";
import { resetReadingStateBus, setReadingStateOwner } from "../hooks/useReadingState";
import { resetForkLineage } from "../workspace/forkLineage";

// The actual reader, owner bridges and auth lifecycle run. Unrelated voice,
// AI and companion widgets are omitted; only the HTTP boundary is synthetic.
vi.mock("../modes/shared/FloatMenu/FloatMenu", () => ({ default: () => null }));
vi.mock("../modes/Reading/TalkToBook", () => ({ default: () => null }));
vi.mock("../modes/Reading/VoiceNote", () => ({ default: () => null }));
vi.mock("../modes/Reading/ResearchThis", () => ({ default: () => null }));
vi.mock("../modes/Reading/ReadingCompanion", () => ({ default: () => null }));
vi.mock("../modes/Reading/ForkProvenance", () => ({ default: () => null }));
vi.mock("../modes/Reading/island/ThreadIsland", () => ({ default: () => null }));
import BookReader from "../modes/Reading";

const documentId = "private-retirement-book";
const privateText = "A private passage already open before logout.";
const detail: BookDetail = {
  document_id: documentId, title: "A private title", author: null,
  servability: "personal_readable", servable_full_text: false, page_count: 1,
  cover_uri: null, ip_holder_id: null, taken_down: false, pagination_scheme: "pdf_page",
  provenance: null, license_basis: null, toc: [],
};
const body: FullTextResponse = {
  document_id: documentId, title: detail.title, author: null, servability: "personal_readable",
  servable: false, full_text: `## Page 1\n\n${privateText}`, snippet: null,
  reason: "owner_personal_reading", tier: null, ad_eligible: false, canonical_url: null, license: null,
};
function response(status: number, payload: unknown = {}): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}
function identity(): Response {
  return response(200, { user_id: "account-a", email: null, auth_method: "magic_link" });
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("deferred not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
let controller: AuthContextValue | null;
let authReply: () => Promise<Response>;
let logoutReply: () => Promise<Response>;
const fetches = vi.fn<typeof fetch>();
function auth(): AuthContextValue {
  if (controller === null) throw new Error("auth consumer has not mounted");
  return controller;
}
function ReaderView() {
  const current = useAuth();
  const [open, setOpen] = useState(false);
  useEffect(() => { controller = current; }, [current]);
  const key = notebookDraftKey("retirement-draft");
  return <>
    <output data-testid="retirement-identity">{current.state.status === "authenticated" ? current.state.identity.user_id : current.state.status}</output>
    <input aria-label="A local unsaved draft" defaultValue={key ? localStorage.getItem(key) ?? "" : ""} />
    <button onClick={() => setOpen(true)}>Open private book</button>
    {/* Deliberately mounted independently of RequireAuth. */}
    {open && <BookReader documentId={documentId} />}
  </>;
}
function mount() {
  return render(<MemoryRouter initialEntries={[`/read/${documentId}`]}><AuthProvider><ReaderView /></AuthProvider></MemoryRouter>);
}
function identityCalls() {
  return fetches.mock.calls.filter(([input]) => String(input).endsWith("/auth/me")).length;
}
function bodyCalls() {
  return fetches.mock.calls.filter(([input]) => String(input).endsWith("/owner-full-text")).length;
}
function expectPrivateBodyHidden() {
  const text = screen.queryByText(privateText);
  expect(text === null || isInaccessible(text)).toBe(true);
  expect(formatReadingFocusSystemContext()).toBeNull();
}
beforeEach(() => {
  setWorkspaceOwner(null);
  setReadingStateOwner(null);
  resetReadingStateBus();
  resetForkLineage();
  clearReadingFocus();
  window.localStorage.clear();
  window.sessionStorage.clear();
  controller = null;
  authReply = async () => identity();
  logoutReply = async () => new Response(null, { status: 204 });
  fetches.mockReset().mockImplementation(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/auth/logout") return logoutReply();
    if (path === "/auth/claim") return response(200, { setup_passkey: false, next: "/" });
    if (path === "/health") return response(200);
    if (path === `/books/${documentId}`) return response(200, detail);
    if (path.endsWith("/owner-full-text") || path.endsWith("/full-text")) return response(200, body);
    if (path === "/books") return response(200, { books: [], count: 0 });
    if (path.endsWith("/anchors")) return response(200, { document_id: documentId, anchors: [], count: 0 });
    if (path.endsWith("/reading-state")) return response(404);
    if (path.endsWith("/forks")) return response(200, { forks: [], forked_from: null });
    if (path.includes("/anchor-map")) return response(200, { document_id: documentId, chunks: [], complete: true });
    throw new Error(`Unexpected private retirement control request: ${path}`);
  });
  vi.stubGlobal("fetch", fetches);
});
afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  setReadingStateOwner(null);
  resetReadingStateBus();
  resetForkLineage();
  clearReadingFocus();
  vi.unstubAllGlobals();
});

describe("mounted auth logout survives failed local retirement", () => {
  it("hides the open A body, denies old work, preserves A's flush and permits genuinely confirmed recovery", async () => {
    mount();
    await screen.findByText("account-a");
    const captured = workspaceOwnerSession();
    const key = notebookDraftKey("retirement-draft", captured);
    if (key === null) throw new Error("A must own its local partition");
    const draft = screen.getByRole("textbox", { name: "A local unsaved draft" });
    fireEvent.change(draft, { target: { value: "A unsaved draft must survive" } });
    const outbound = vi.fn();
    const primary = new Error("controlled retirement failure");
    // Registered after A admission but before the reader's retirement hooks.
    const unsubscribe = beforeWorkspaceOwnerChange(() => {
      expect(workspaceOwnerSession().subject).toBe("account-a");
      if (isWorkspaceOwnerSession(captured)) outbound();
      if (!(draft instanceof HTMLInputElement)) throw new Error("draft input missing");
      localStorage.setItem(key, draft.value);
      throw primary;
    });
    try {
      fireEvent.click(screen.getByRole("button", { name: "Open private book" }));
      await screen.findByText(privateText, {}, { timeout: 10000 });
      expect(formatReadingFocusSystemContext()).toContain(privateText);
      const reads = bodyCalls();
      await act(async () => { await expect(auth().signOut()).rejects.toBe(primary); });
      expectPrivateBodyHidden();
      expect(screen.getByRole("alert").textContent).toContain("local cleanup");
      expect(outbound).not.toHaveBeenCalled();
      expect(isWorkspaceOwnerSession(captured)).toBe(false);
      expect(localStorage.getItem(key)).toBe("A unsaved draft must survive");
      const requests = identityCalls();
      await act(async () => { await auth().refresh(); });
      expect(identityCalls()).toBe(requests + 1);
      expectPrivateBodyHidden();
      expect(bodyCalls()).toBe(reads);
    } finally {
      unsubscribe();
    }
    const confirmed = deferred<Response>();
    authReply = () => confirmed.promise;
    let pending: Promise<void> | null = null;
    await act(async () => {
      expect((await claimLogin("private-unit-attempt", "private-unit-claim", "1234")).status).toBe("authenticated");
      pending = auth().refresh({ afterSignIn: true });
    });
    expectPrivateBodyHidden();
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
    await act(async () => { confirmed.resolve(identity()); await pending; });
    await screen.findByRole("button", { name: "Open private book" });
    expect(screen.getByRole("textbox", { name: "A local unsaved draft" })).toHaveProperty("value", "A unsaved draft must survive");
    expect(workspaceOwnerSession()).not.toBe(captured);
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Open private book" }));
    await screen.findByText(privateText, {}, { timeout: 10000 });
  }, 15000);

  it("retains local and server failures separately while still attempting real server logout", async () => {
    mount();
    await screen.findByText("account-a");
    const primary = new Error("controlled cleanup failure");
    const secondary = new TypeError("controlled server logout rejection");
    const unsubscribe = beforeWorkspaceOwnerChange(() => { throw primary; });
    logoutReply = async () => { throw secondary; };
    try {
      fireEvent.click(screen.getByRole("button", { name: "Open private book" }));
      await screen.findByText(privateText, {}, { timeout: 10000 });
      await act(async () => {
        try { await auth().signOut(); throw new Error("logout unexpectedly succeeded"); }
        catch (error) {
          expect(error).toBeInstanceOf(AggregateError);
          if (!(error instanceof AggregateError)) throw error;
          expect(error.errors).toEqual([primary, secondary]);
        }
      });
      expect(fetches.mock.calls.filter(([input]) => String(input).endsWith("/auth/logout"))).toHaveLength(1);
      expectPrivateBodyHidden();
      expect(screen.getByRole("alert").textContent).toContain("local cleanup");
    } finally { unsubscribe(); }
  }, 15000);

  it("hides failed cleanup while logout is pending and retires an older identity reply", async () => {
    mount();
    await screen.findByText("account-a");
    const primary = new Error("controlled retirement failure");
    const unsubscribe = beforeWorkspaceOwnerChange(() => { throw primary; });
    try {
      fireEvent.click(screen.getByRole("button", { name: "Open private book" }));
      await screen.findByText(privateText, {}, { timeout: 10000 });
      const old = deferred<Response>();
      authReply = () => old.promise;
      let refresh: Promise<void> | null = null;
      act(() => { refresh = auth().refresh(); });
      const logout = deferred<Response>();
      logoutReply = () => logout.promise;
      let pending: Promise<void> | null = null;
      act(() => { pending = auth().signOut().catch((error: unknown) => { expect(error).toBe(primary); }); });
      expectPrivateBodyHidden();
      const before = identityCalls();
      await act(async () => { await auth().refresh(); window.dispatchEvent(new Event("focus")); });
      expect(identityCalls()).toBe(before);
      await act(async () => { old.resolve(identity()); await refresh; });
      expectPrivateBodyHidden();
      await act(async () => { logout.resolve(new Response(null, { status: 204 })); await pending; });
      await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("local cleanup"));
      expectPrivateBodyHidden();
    } finally { unsubscribe(); }
  }, 15000);
});
