import { useEffect } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BookDetail, FullTextResponse } from "../../api/books";
import type { BookAnchor } from "../../lib/api";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import { setWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { clearReadingFocus, formatReadingFocusSystemContext } from "../../lib/readingFocus";
import { resetReadingStateBus, setReadingStateOwner } from "../../hooks/useReadingState";
import { resetForkLineage } from "../../workspace/forkLineage";

// Omit unrelated AI, voice and companion widgets. The body loader, rendered
// ReadingColumn, AuthProvider, owner bridge, anchors and API helpers are real.
vi.mock("../shared/FloatMenu/FloatMenu", () => ({ default: () => null }));
vi.mock("./TalkToBook", () => ({ default: () => null }));
vi.mock("./VoiceNote", () => ({ default: () => null }));
vi.mock("./ResearchThis", () => ({ default: () => null }));
vi.mock("./ReadingCompanion", () => ({ default: () => null }));
vi.mock("./ForkProvenance", () => ({ default: () => null }));
vi.mock("./island/ThreadIsland", () => ({ default: () => null }));
import BookReader from "./index";

// Synthetic HTTP-boundary controls, not live signed-account/book evidence.
const documentId = "shared-book";
const privateText = "A private owner-readable passage.";
const detail: BookDetail = {
  document_id: documentId, title: "A private book title", author: null,
  servability: "personal_readable", servable_full_text: false, page_count: 1,
  cover_uri: null, ip_holder_id: null, taken_down: false, pagination_scheme: "pdf_page",
  provenance: null, license_basis: null, toc: [],
};
const body: FullTextResponse = {
  document_id: documentId, title: detail.title, author: null, servability: "personal_readable",
  servable: false, full_text: `## Page 1\n\n${privateText}`, snippet: null,
  reason: "owner_personal_reading", tier: null, ad_eligible: false, canonical_url: null, license: null,
};
const orphan: BookAnchor = {
  anchor_id: "a-private-anchor", document_id: documentId,
  anchor: { normalization: "unicode-nfc-v1", node_id: "a-chunk", node_text_sha256: "a".repeat(64),
    start_scalar: 0, end_scalar: 15, quote: "A private quote", prefix: null, suffix: null },
  servable_at_pin: true, selection_text_sha256: "b".repeat(64), page_index_hint: 0,
  source: "pin", status: "orphaned", exact_valid: false, investigation_id: "a-private-research",
  created_at: "2026-10-06T00:00:00Z", updated_at: "2026-10-06T00:00:00Z",
};
function response(status: number, payload: unknown = {}): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}
function identity(subject: string): Response {
  return response(200, { user_id: subject, email: null, auth_method: "magic_link" });
}
function anchorList(anchors: BookAnchor[]): Response {
  return response(200, { document_id: documentId, anchors, count: anchors.length });
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("deferred not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
let authReply: () => Promise<Response>;
let logoutReply: () => Promise<Response>;
let detailReply: () => Promise<Response>;
let bodyReply: () => Promise<Response>;
let anchorReply: () => Promise<Response>;
let controller: AuthContextValue | null = null;
const fetches = vi.fn<typeof fetch>();
function auth(): AuthContextValue {
  if (controller === null) throw new Error("auth consumer has not mounted");
  return controller;
}
function ReaderView() {
  const current = useAuth();
  useEffect(() => { controller = current; }, [current]);
  return <>
    <output data-testid="reader-identity">{current.state.status === "authenticated" ? current.state.identity.user_id : current.state.status}</output>
    {/* Intentionally stay mounted outside RequireAuth to exercise reader admission itself. */}
    <BookReader documentId={documentId} />
  </>;
}
function mount() {
  return render(<MemoryRouter initialEntries={[`/read/${documentId}`]}><AuthProvider><ReaderView /></AuthProvider></MemoryRouter>);
}
function bodyReadCount() {
  return fetches.mock.calls.filter(([input]) => String(input).endsWith(`/books/${documentId}/owner-full-text`)).length;
}
function expectNoAPrivateState() {
  expect(document.body.textContent).not.toContain(privateText);
  expect(document.body.textContent).not.toContain(detail.title);
  expect(document.querySelector('[data-orphaned-anchor="a-private-anchor"]')).toBeNull();
  expect(document.querySelector('a[href="/inv/a-private-research"]')).toBeNull();
  expect(formatReadingFocusSystemContext() ?? "").not.toContain(privateText);
}
async function refresh(subject: string) {
  authReply = async () => identity(subject);
  await act(async () => { await auth().refresh(); });
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
  authReply = async () => identity("account-a");
  logoutReply = async () => new Response(null, { status: 204 });
  detailReply = async () => response(200, detail);
  bodyReply = async () => response(200, body);
  anchorReply = async () => anchorList([]);
  fetches.mockReset().mockImplementation(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/auth/logout") return logoutReply();
    if (path === "/health") return response(200);
    if (path === `/books/${documentId}`) return detailReply();
    if (path === `/books/${documentId}/owner-full-text` || path === `/books/${documentId}/full-text`) return bodyReply();
    if (path === "/books") return response(200, { books: [], count: 0 });
    if (path === `/books/${documentId}/anchors`) return anchorReply();
    if (path === `/books/${documentId}/reading-state`) return response(404);
    if (path === `/books/${documentId}/forks`) return response(200, { forks: [], forked_from: null });
    if (path === `/books/${documentId}/anchor-map/owner` || path === `/books/${documentId}/anchor-map`) {
      return response(200, { document_id: documentId, chunks: [], complete: true });
    }
    throw new Error(`Unexpected reader source-control request: ${path}`);
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

describe("real authenticated reader retires private body and derived state", () => {
  it("keeps the authorized A body and page context across a same-A verification", async () => {
    mount();
    await screen.findByText(privateText, {}, { timeout: 10000 });
    expect(formatReadingFocusSystemContext()).toContain(privateText);
    expect(bodyReadCount()).toBe(1);
    await refresh("account-a");
    expect(screen.getByText(privateText)).not.toBeNull();
    expect(formatReadingFocusSystemContext()).toContain(privateText);
    expect(bodyReadCount()).toBe(1);
    const request = fetches.mock.calls.find(([input]) => String(input).endsWith("/owner-full-text"));
    expect(request?.[1]?.credentials).toBe("include");
  }, 15000);

  it("pending logout cannot reload the old A cookie and immediately retires TP page context", async () => {
    mount();
    await screen.findByText(privateText, {}, { timeout: 10000 });
    const held = deferred<Response>();
    logoutReply = () => held.promise;
    const before = bodyReadCount();
    let pending: Promise<void> | null = null;
    let immediateContext: string | null = "not retired";
    act(() => { pending = auth().signOut(); immediateContext = formatReadingFocusSystemContext(); });
    expect(immediateContext).toBeNull();
    expectNoAPrivateState();
    await act(async () => { window.dispatchEvent(new Event("focus")); await auth().refresh(); });
    // The fetch fixture would still serve A on any new cookie-bearing read.
    expect(bodyReadCount()).toBe(before);
    expect(workspaceOwnerSession().subject).toBeNull();
    expectNoAPrivateState();
    await act(async () => { held.resolve(new Response(null, { status: 204 })); await pending; });
    await refresh("account-a");
    expect(bodyReadCount()).toBe(before);
    expectNoAPrivateState();
  }, 15000);

  it.each([
    { name: "rejected logout", reply: async (): Promise<Response> => { throw new TypeError("controlled logout rejection"); } },
    { name: "non-2xx logout", reply: async () => response(503) },
  ])("$name keeps a fresh old-cookie A success outside reader admission", async ({ reply }) => {
    mount();
    await screen.findByText(privateText, {}, { timeout: 10000 });
    const before = bodyReadCount();
    logoutReply = reply;
    await act(async () => { await expect(auth().signOut()).rejects.toThrow(); });
    await refresh("account-a");
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(bodyReadCount()).toBe(before);
    expectNoAPrivateState();
  }, 15000);

  it("B's same-book 401 remains denied after an older A body success arrives", async () => {
    const old = deferred<Response>();
    bodyReply = () => old.promise;
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    await waitFor(() => expect(bodyReadCount()).toBe(1), { timeout: 10000 });
    detailReply = async () => response(401);
    bodyReply = async () => response(401);
    await refresh("account-b");
    await screen.findByRole("alert", {}, { timeout: 10000 });
    expectNoAPrivateState();
    await act(async () => { old.resolve(response(200, body)); });
    expect(screen.getByTestId("reader-identity").textContent).toBe("account-b");
    expectNoAPrivateState();
  }, 15000);

  it("loaded A anchor ids and private links retire when B reads the same public body", async () => {
    const sharedDetail: BookDetail = { ...detail, title: "Shared public book", servability: "public_domain", servable_full_text: true };
    const sharedBody: FullTextResponse = { ...body, title: sharedDetail.title, servability: "public_domain", servable: true,
      full_text: "## Page 1\n\nShared readable passage.", reason: "servable" };
    detailReply = async () => response(200, sharedDetail);
    bodyReply = async () => response(200, sharedBody);
    anchorReply = async () => anchorList([orphan]);
    mount();
    await screen.findByText("Shared readable passage.", {}, { timeout: 10000 });
    await waitFor(() => expect(document.querySelector('[data-orphaned-anchor="a-private-anchor"]')).not.toBeNull(), { timeout: 10000 });
    expect(document.querySelector('a[href="/inv/a-private-research"]')).not.toBeNull();
    const b = deferred<Response>();
    anchorReply = () => b.promise;
    await refresh("account-b");
    expect(document.querySelector('[data-orphaned-anchor="a-private-anchor"]')).toBeNull();
    expect(document.querySelector('a[href="/inv/a-private-research"]')).toBeNull();
    await screen.findByText("Shared readable passage.", {}, { timeout: 10000 });
    await act(async () => { b.resolve(anchorList([])); });
    expect(document.querySelector('[data-orphaned-anchor="a-private-anchor"]')).toBeNull();
    expect(document.querySelector('a[href="/inv/a-private-research"]')).toBeNull();
  }, 15000);
});
