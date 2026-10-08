import { useEffect, useState } from "react";
import { act, cleanup, fireEvent, isInaccessible, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BookDetail, FullTextResponse } from "../../api/books";
import type { ReadingState } from "../../api/readingState";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import { isWorkspaceOwnerSession, setWorkspaceOwner, subscribeWorkspaceOwnerAdmission, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { resetReadingStateBus, setReadingStateOwner, useReadingStateBus } from "../../hooks/useReadingState";
import { positionStorageKey } from "./usePosition";
import { clearReadingFocus } from "../../lib/readingFocus";
import { resetForkLineage } from "../../workspace/forkLineage";

// Actual AuthProvider, reader, dwell, bus and HTTP serializers. Only external
// HTTP responses and unrelated companion widgets are synthetic unit controls.
vi.mock("../shared/FloatMenu/FloatMenu", () => ({ default: () => null }));
vi.mock("./TalkToBook", () => ({ default: () => null }));
vi.mock("./VoiceNote", () => ({ default: () => null }));
vi.mock("./ResearchThis", () => ({ default: () => null }));
vi.mock("./ReadingCompanion", () => ({ default: () => null }));
vi.mock("./ForkProvenance", () => ({ default: () => null }));
vi.mock("./island/ThreadIsland", () => ({ default: () => null }));
import BookReader from "./index";

const id = "admission-unit-book";
const passages = ["Admission unit first passage.", "Admission unit second passage.", "Admission unit third passage."];
const detail: BookDetail = {
  document_id: id, title: "Admission unit book", author: null,
  servability: "public_domain", servable_full_text: true, page_count: 3,
  cover_uri: null, ip_holder_id: null, taken_down: false, pagination_scheme: "pdf_page",
  provenance: null, license_basis: null, toc: [],
};
const body: FullTextResponse = {
  document_id: id, title: detail.title, author: null, servability: "public_domain",
  servable: true, full_text: passages.map((p, i) => `## Page ${i + 1}\n\n${p}`).join("\n\n"),
  snippet: null, reason: "servable", tier: null, ad_eligible: false, canonical_url: null, license: null,
};
function reply(status: number, value: unknown = {}): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}
function identity(subject = "account-a"): Response {
  return reply(200, { user_id: subject, email: null, auth_method: "magic_link" });
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("Uninitialized gate"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
function row(subject: string, page: number): ReadingState {
  return { document_id: id, page_index: page, anchor_ref: `anchor-${subject}`, prefs: {}, revision: 2, updated_at: "unit-baseline" };
}
let clock: number;
let controller: AuthContextValue | null;
let authReply: () => Promise<Response>;
let stateReply: ((value: ReadingState) => Promise<Response>) | null;
let writeReply: ((value: ReadingState) => Promise<Response>) | null;
let actor: string;
let rows: Map<string, ReadingState>;
let writes: Array<{ actor: string; body: unknown }>;
let events: unknown[];
const fetches = vi.fn<typeof fetch>();
const disposers: Array<() => void> = [];
function auth() {
  if (!controller) throw new Error("Auth consumer is not mounted");
  return controller;
}
function ReaderView() {
  const current = useAuth();
  const [open, setOpen] = useState(false);
  useEffect(() => { controller = current; }, [current]);
  return <>
    <output>{current.state.status === "authenticated" ? current.state.identity.user_id : current.state.status}</output>
    <button onClick={() => setOpen(true)}>Open admission book</button>
    {open && <BookReader documentId={id} />}
  </>;
}
async function mount() {
  const view = render(<MemoryRouter><AuthProvider><ReaderView /></AuthProvider></MemoryRouter>);
  await screen.findByText("account-a");
  fireEvent.click(screen.getByRole("button", { name: "Open admission book" }));
  await screen.findByText(passages[0]);
  return view;
}
function stateGetCount() {
  return fetches.mock.calls.filter(([input, init]) => String(input).endsWith("/reading-state") && init?.method !== "PUT").length;
}
function assertHidden() {
  const passage = screen.queryByText(passages[1]);
  expect(passage === null || isInaccessible(passage)).toBe(true);
}
beforeEach(() => {
  setWorkspaceOwner(null); setReadingStateOwner(null); resetReadingStateBus();
  resetForkLineage(); clearReadingFocus();
  localStorage.clear(); sessionStorage.clear();
  clock = 0; controller = null; actor = "account-a";
  authReply = async () => identity(); stateReply = null; writeReply = null;
  rows = new Map([["account-a", row("a", 0)], ["account-b", row("b", 2)]]);
  writes = []; events = [];
  vi.spyOn(performance, "now").mockImplementation(() => clock);
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  fetches.mockReset().mockImplementation(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/health") return reply(200);
    if (path === `/books/${id}`) return reply(200, detail);
    if (path.endsWith("/owner-full-text") || path.endsWith("/full-text")) return reply(200, body);
    if (path === "/books") return reply(200, { books: [], count: 0 });
    if (path.endsWith("/reading-state")) {
      const stored = rows.get(actor);
      if (!stored) return reply(404);
      if (init?.method !== "PUT") return stateReply ? stateReply({ ...stored }) : reply(200, stored);
      if (typeof init.body !== "string") throw new Error("Missing serialized position body");
      const value: unknown = JSON.parse(init.body);
      writes.push({ actor, body: value });
      if (value === null || typeof value !== "object"
        || !("page_index" in value) || typeof value.page_index !== "number" || !Number.isSafeInteger(value.page_index)
        || !("revision" in value) || typeof value.revision !== "number" || !Number.isSafeInteger(value.revision)
        || !("anchor_ref" in value) || !(value.anchor_ref === null || typeof value.anchor_ref === "string")
        || !("prefs" in value) || value.prefs === null || typeof value.prefs !== "object"
        || Array.isArray(value.prefs) || Object.keys(value.prefs).length !== 0) throw new TypeError("Malformed unit position request");
      if (value.revision !== stored.revision) return reply(409);
      const written = { ...stored, page_index: value.page_index, anchor_ref: value.anchor_ref, revision: stored.revision + 1, updated_at: "unit-written" };
      rows.set(actor, written);
      return writeReply ? writeReply(written) : reply(200, written);
    }
    if (path.endsWith("/anchors")) return reply(200, { document_id: id, anchors: [], count: 0 });
    if (path.includes("/anchor-map")) return reply(200, { document_id: id, chunks: [], complete: true });
    if (path.endsWith("/forks")) return reply(200, { forks: [], forked_from: null });
    if (path.endsWith("/events/typed") && typeof init?.body === "string") {
      events.push(JSON.parse(init.body)); return reply(200, { event_id: "unit-read" });
    }
    throw new Error(`Unexpected unit endpoint: ${path}`);
  });
  vi.stubGlobal("fetch", fetches);
});
afterEach(() => {
  for (const dispose of disposers.splice(0)) dispose();
  cleanup(); setWorkspaceOwner(null); setReadingStateOwner(null); resetReadingStateBus();
  resetForkLineage(); clearReadingFocus(); vi.restoreAllMocks(); vi.unstubAllGlobals();
});

describe("mounted AuthProvider reading admission", () => {
  it("excludes hidden verification dwell and resumes A's retained local turn only after same-token confirmation", async () => {
    await mount();
    await waitFor(() => expect(useReadingStateBus.getState().byDocument[id]?.revision).toBe(2));
    const captured = workspaceOwnerSession();
    clock = 5_000;
    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    await screen.findByText(passages[1]);
    const verification = deferred<Response>(); authReply = () => verification.promise;
    clock = 10_000;
    let pending: Promise<void> | undefined;
    act(() => { pending = auth().refresh(); });
    assertHidden();
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
    expect(sessionStorage.getItem(positionStorageKey(id))).toBe("1");
    await act(async () => { await new Promise((done) => setTimeout(done, 500)); });
    clock = 40_000;
    act(() => window.dispatchEvent(new Event("pagehide")));
    expect(writes).toEqual([]); expect(events).toEqual([]);
    await act(async () => { verification.resolve(identity()); await pending; });
    expect(workspaceOwnerSession()).toBe(captured);
    await waitFor(() => expect(writes).toEqual([{ actor: "account-a", body: { page_index: 1, anchor_ref: "anchor-a", prefs: {}, revision: 2 } }]));
    expect(screen.getByText(passages[1])).not.toBeNull();
    clock = 45_000;
    await act(async () => window.dispatchEvent(new Event("pagehide")));
    expect(events).toEqual([]);
    clock = 60_000;
    await act(async () => window.dispatchEvent(new Event("pagehide")));
    expect(events).toEqual([expect.objectContaining({ document_id: id, payload: expect.objectContaining({ action_type: "source.read", dwell_ms: 30_000, page_count: 2 }) })]);
  });

  it("holds an already returned GET through suspension, then adopts the same captured A result", async () => {
    const get = deferred<Response>(); stateReply = () => get.promise;
    await mount();
    const captured = workspaceOwnerSession();
    const verification = deferred<Response>(); authReply = () => verification.promise;
    let pending: Promise<void> | undefined;
    act(() => { pending = auth().refresh(); });
    await act(async () => get.resolve(reply(200, row("a", 2))));
    expect(useReadingStateBus.getState().byDocument[id]?.loaded).toBe(false);
    expect(writes).toEqual([]);
    await act(async () => { verification.resolve(identity()); await pending; });
    await screen.findByText(passages[2]);
    expect(workspaceOwnerSession()).toBe(captured);
    expect(useReadingStateBus.getState().byDocument[id]).toMatchObject({ revision: 2, anchorRef: "anchor-a", pageIndex: 2 });
    expect(writes).toEqual([]);
  });

  it("refuses A's already dispatched late PUT after the real auth bridge replaces A with B", async () => {
    await mount();
    await waitFor(() => expect(useReadingStateBus.getState().byDocument[id]?.revision).toBe(2));
    const put = deferred<Response>(); writeReply = () => put.promise;
    const captured = workspaceOwnerSession();
    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    authReply = async () => { actor = "account-b"; return identity("account-b"); };
    await act(async () => auth().refresh());
    await screen.findByText("account-b");
    fireEvent.click(screen.getByRole("button", { name: "Open admission book" }));
    await screen.findByText(passages[2]);
    await act(async () => put.resolve(reply(200, { ...row("a", 1), revision: 3 })));
    expect(workspaceOwnerSession()).not.toBe(captured);
    expect(useReadingStateBus.getState().byDocument[id]).toMatchObject({ revision: 2, anchorRef: "anchor-b", pageIndex: 2 });
    expect(rows.get("account-b")).toEqual(row("b", 2));
    expect(writes).toHaveLength(1); expect(writes[0]?.actor).toBe("account-a");
    expect(events).toEqual([]);
  });

  it("does not dispatch from an early ready observer when a later observer fails confirmation", async () => {
    await mount();
    await waitFor(() => expect(useReadingStateBus.getState().byDocument[id]?.loaded).toBe(true));
    const before = stateGetCount();
    disposers.push(subscribeWorkspaceOwnerAdmission((event) => {
      if (event.state === "ready") void useReadingStateBus.getState().load(id);
    }));
    disposers.push(subscribeWorkspaceOwnerAdmission((event) => {
      if (event.state === "ready") throw new Error("Synthetic late ready observer failure");
    }));
    await act(async () => auth().refresh());
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(false);
    expect(stateGetCount()).toBe(before);
    expect(writes).toEqual([]); expect(events).toEqual([]);
  });
});
