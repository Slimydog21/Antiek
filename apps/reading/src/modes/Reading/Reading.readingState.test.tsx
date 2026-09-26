/**
 * Reading.readingState.test.tsx — reading-state bus proofs (reading-global
 * SPR-01), the real hook against a mocked-but-stateful transport.
 *
 *   2. SHARED POSITION: the standalone route and a window-mounted reader
 *      (the renderWindowReader harness) share ONE position through the
 *      client store — turn the page in one mount, the other shows it.
 *      There is no mount-to-mount signaling to test because none exists:
 *      both mounts read the same zustand slice.
 *   3. DEGRADATION: a failing transport never blocks reading — the
 *      sessionStorage fallback keeps position working; an unsettled local
 *      turn survives recovery and retries with the server revision. The
 *      competing-device 409 proof exercises the substrate-wins rule.
 *   4. CLAMP: a stored position past a shortened book snaps to the last
 *      page on load (usePosition's clamp, now against server-held values).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { WindowHostProvider } from "../../components/windows/windowHostContext";
import {
  resetReadingStateBus,
  setReadingStateOwner,
  useReadingState,
  useReadingStateBus,
} from "../../hooks/useReadingState";
import { positionStorageKey, readingPositionOwner } from "./usePosition";
import { AuthProvider, useAuth } from "../../lib/auth";

const {
  getBookMock,
  getFullTextMock,
  listBooksMock,
  useInvestigationMock,
  postTypedEventMock,
  searchBlocksMock,
  apiFetchMock,
} = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  useInvestigationMock: vi.fn(),
  postTypedEventMock: vi.fn((_e: unknown) => Promise.resolve({ event_id: "e" })),
  searchBlocksMock: vi.fn((_q: string) => Promise.resolve({ count: 0, hits: [] })),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
  };
});

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (e: unknown) => postTypedEventMock(e),
    searchBlocks: (q: string) => searchBlocksMock(q),
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));

const BODY =
  "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.";

function makeDetail(over: Partial<BookDetail> = {}): BookDetail {
  return {
    document_id: "doc-1",
    title: "A Servable Book",
    author: "Auth",
    servability: "public_domain",
    servable_full_text: true,
    page_count: 2,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
    pagination_scheme: "pdf_page",
    provenance: null,
    license_basis: null,
    toc: [{ title: "Chapter 1", page_index: 0, level: 0 }],
    ...over,
  };
}

function makeBody(over: Partial<FullTextResponse> = {}): FullTextResponse {
  return {
    document_id: "doc-1",
    servable: true,
    servability: "public_domain",
    full_text: BODY,
    snippet: null,
    title: "A Servable Book",
    author: "Auth",
    reason: "servable",
    tier: null,
    ad_eligible: true,
    canonical_url: null,
    license: null,
    ...over,
  };
}

// ── A tiny stateful reading-state server ──────────────────────────────────

interface BusRow {
  page_index: number;
  anchor_ref: string | null;
  prefs: Record<string, unknown>;
  revision: number;
  updated_at: string;
}

interface BusServer {
  row: BusRow | null;
  puts: { page_index: number; revision: number }[];
  /** When true, every bus call fails (the degradation drill). */
  down: boolean;
  getGate?: Promise<void>;
  putGate?: Promise<void>;
}

function gate() {
  let release: () => void = () => {};
  const promise = new Promise<void>((resolve) => { release = resolve; });
  return { promise, release };
}

function route(server: BusServer) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;

    if (url.endsWith("/reading-state")) {
      if (server.down) return jsonResponse({ detail: "bus down" }, 500);
      if (method === "GET") {
        const snapshot = server.row ? { ...server.row } : null;
        if (server.getGate) await server.getGate;
        if (!snapshot) return jsonResponse({ detail: "reading_state_not_found" }, 404);
        return jsonResponse({ document_id: "doc-1", ...snapshot });
      }
      if (method === "PUT") {
        const expected = parsedBody?.revision ?? -1;
        const current = server.row?.revision ?? 0;
        if (expected !== current) {
          return jsonResponse({ detail: "reading_state_stale_revision" }, 409);
        }
        server.puts.push({ page_index: parsedBody.page_index, revision: expected });
        server.row = {
          page_index: parsedBody.page_index,
          anchor_ref: parsedBody.anchor_ref ?? null,
          prefs: parsedBody.prefs ?? {},
          revision: current + 1,
          updated_at: "2026-09-25T12:00:00Z",
        };
        const written = { ...server.row };
        if (server.putGate) await server.putGate;
        return jsonResponse({ document_id: "doc-1", ...written });
      }
    }
    if (url.endsWith("/anchors") && method === "GET") {
      return jsonResponse({ document_id: "doc-1", anchors: [], count: 0 });
    }
    if (url.endsWith("/anchor-map")) {
      return jsonResponse({
        document_id: "doc-1",
        chunks: [
          { chunk_id: "c-1", section_path: "Page 1", body_start: 11, body_end: 33, node_text_sha256: "h".repeat(64) },
        ],
        complete: true,
      });
    }
    if (url.includes("/sessions/")) {
      return jsonResponse({ detail: "not a session" }, 404);
    }
    if (url.includes("/investigations")) {
      return jsonResponse({ count: 0, investigations: [] });
    }
    return jsonResponse({ text: "reply" });
  });
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function busServer(row: BusRow | null = null): BusServer {
  return { row, puts: [], down: false };
}

async function renderReader() {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/read/doc-1"]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** BOTH mounts at once: the standalone route AND the window-mounted reader,
 *  one render tree, one client store. */
async function renderBothMounts() {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/read/doc-1"]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
      <WindowHostProvider value={true}>
        <BookReader documentId="doc-1" />
      </WindowHostProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.removeItem("antiek.island.hidden");
  vi.stubGlobal("fetch", apiFetchMock);
  apiFetchMock.mockReset();
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
  useInvestigationMock.mockReset().mockReturnValue({
    id: "read-doc-1",
    status: "not_found",
    events: [],
    question: null,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    reconnects: 0,
  });
  useWorkspace.getState().reset();
  resetReadingStateBus();
  setReadingStateOwner("reader-a");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ── Proof 2: one position, two mounts, one store ──────────────────────────

describe("one position per owner+document", () => {
  it("standalone route + window-mounted reader share ONE position through the client store — a turn in one mount shows in the other", async () => {
    const server = busServer();
    route(server);
    await renderBothMounts();

    // Both mounts land on page 1 (no server row yet — the sessionStorage
    // seed, page 0).
    await waitFor(() =>
      expect(screen.getAllByText("The opening of the book.")).toHaveLength(2),
    );

    // Turn the page in ONE mount (the first pager on screen).
    fireEvent.click(screen.getAllByText("Next →")[0]);

    // The OTHER mount shows the same page — it read the same store, never
    // a signal from its sibling.
    await waitFor(() =>
      expect(screen.getAllByText("The second page.")).toHaveLength(2),
    );
    expect(screen.queryByText("The opening of the book.")).toBeNull();

    // ONE debounced write-through hit the bus (one store, one write), with
    // the optimistic-concurrency revision of a first write.
    await waitFor(() => expect(server.puts).toHaveLength(1));
    expect(server.puts[0]).toEqual({ page_index: 1, revision: 0 });
    expect(server.row?.revision).toBe(1);
  });
});

// ── Proof 3: degradation — the bus never blocks reading ───────────────────

describe("degradation and recovery", () => {
  it("a failed transport keeps its turn and retries it when the bus recovers", async () => {
    const server = busServer();
    server.down = true;
    route(server);
    await renderReader();
    await screen.findByText("The opening of the book.");

    // The bus is down: the page turn still works (the sessionStorage
    // fallback layer), and the failed write is marked, never blocking.
    fireEvent.click(screen.getByText("Next →"));
    await screen.findByText("The second page.");
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBe("1");
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(
          ([u, i]) =>
            String(u).endsWith("/reading-state") &&
            (i as { method?: string } | undefined)?.method === "PUT",
        ),
      ).toBe(true),
    );
    expect(server.row).toBeNull(); // nothing reached the server

    // Recovery: the server has a competing value written during the outage.
    // The focus GET proves connectivity, then the still-pending local turn
    // retries with that revision; connectivity alone does not erase it.
    server.down = false;
    server.row = {
      page_index: 0,
      anchor_ref: null,
      prefs: {},
      revision: 1,
      updated_at: "2026-09-25T12:00:00Z",
    };
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(server.puts).toEqual([{ page_index: 1, revision: 1 }]));
    await screen.findByText("The second page.");
    expect(server.row?.page_index).toBe(1);
    expect(server.row?.revision).toBe(2);
  });
});

// ── Proof 4: clamp-on-shrink against a server-held value ──────────────────

describe("the clamp rule", () => {
  it("a stored position past a shortened book snaps to the last page on load", async () => {
    const server = busServer({
      page_index: 5,
      anchor_ref: null,
      prefs: {},
      revision: 3,
      updated_at: "2026-09-25T12:00:00Z",
    });
    route(server);
    await renderReader();

    // The book has 2 pages; the server says page 5. The reader clamps to
    // the last page — never an out-of-range render.
    await screen.findByText("The second page.");
    expect(screen.queryByText("The opening of the book.")).toBeNull();
  });
});

describe("local turns and asynchronous server work", () => {
  const initialRow: BusRow = {
    page_index: 0, anchor_ref: null, prefs: {}, revision: 3,
    updated_at: "2026-09-25T12:00:00Z",
  };

  it("keeps a turn made during an older GET and writes with the fetched revision", async () => {
    const server = busServer({ ...initialRow });
    const held = gate();
    server.getGate = held.promise;
    route(server);
    await renderBothMounts();
    await waitFor(() => expect(apiFetchMock.mock.calls.filter(([u]) => String(u).endsWith("/reading-state"))).toHaveLength(1));
    fireEvent.click(screen.getAllByText("Next →")[0]);
    await waitFor(() => expect(screen.getAllByText("The second page.")).toHaveLength(2));
    held.release();
    await waitFor(() => expect(server.puts).toEqual([{ page_index: 1, revision: 3 }]));
    expect(server.row?.page_index).toBe(1);
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBe("1");
  });

  it("keeps a pending turn when a focus GET starts after the turn", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    await renderBothMounts();
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    const held = gate();
    server.getGate = held.promise;
    fireEvent.click(screen.getAllByText("Next →")[0]);
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(apiFetchMock.mock.calls.filter(([u, i]) => String(u).endsWith("/reading-state") && !i)).toHaveLength(2));
    held.release();
    await waitFor(() => expect(server.puts).toEqual([{ page_index: 1, revision: 3 }]));
    expect(screen.getAllByText("The second page.")).toHaveLength(2);
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBe("1");
  });

  it("serializes a second turn behind an unsettled PUT response", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    await renderBothMounts();
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    const held = gate();
    server.putGate = held.promise;
    fireEvent.click(screen.getAllByText("Next →")[0]);
    await waitFor(() => expect(server.puts).toEqual([{ page_index: 1, revision: 3 }]));
    fireEvent.click(screen.getAllByText("← Previous")[0]);
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(server.puts).toHaveLength(1);
    server.putGate = undefined;
    held.release();
    await waitFor(() => expect(server.puts).toEqual([
      { page_index: 1, revision: 3 }, { page_index: 0, revision: 4 },
    ]));
    expect(server.row?.page_index).toBe(0);
    expect(screen.getAllByText("The opening of the book.")).toHaveLength(2);
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBe("0");
  });

  it("adopts a competing device's row on 409 when no later local turn exists", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    server.row = { ...initialRow, page_index: 6, revision: 4 };
    act(() => result.current.setPageIndex(1));
    await waitFor(() => expect(result.current.pageIndex).toBe(6));
    expect(server.puts).toHaveLength(0);
  });

  it("discards a GET snapshot that returns after a successful local PUT", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    const held = gate();
    server.getGate = held.promise;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(apiFetchMock.mock.calls.filter(([u, i]) => String(u).endsWith("/reading-state") && !i)).toHaveLength(2));
    act(() => result.current.setPageIndex(1));
    await waitFor(() => expect(server.row?.revision).toBe(4));
    held.release();
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(4));
    expect(result.current.pageIndex).toBe(1);
  });

  it("preserves a later turn after a genuine 409", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const routedFetch = apiFetchMock.getMockImplementation();
    const held = gate();
    let heldFirstPut = false;
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      if (init?.method === "PUT" && !heldFirstPut) {
        heldFirstPut = true;
        await held.promise;
      }
      return routedFetch?.(input, init);
    });
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    act(() => result.current.setPageIndex(1));
    await waitFor(() => expect(heldFirstPut).toBe(true));
    act(() => result.current.setPageIndex(2));
    server.row = { ...initialRow, page_index: 6, revision: 4 };
    held.release();
    await waitFor(() => expect(server.row?.page_index).toBe(2));
    expect(server.puts).toEqual([{ page_index: 2, revision: 4 }]);
    expect(result.current.pageIndex).toBe(2);
  });

  it("keeps a pending turn and waits for a new trigger after a non-conflict PUT failure", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const routedFetch = apiFetchMock.getMockImplementation();
    let failedFirstPut = false;
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      if (init?.method === "PUT" && !failedFirstPut) {
        failedFirstPut = true;
        return jsonResponse({ detail: "writer unavailable" }, 503);
      }
      return routedFetch?.(input, init);
    });
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));

    act(() => result.current.setPageIndex(1));
    await waitFor(() => expect(failedFirstPut).toBe(true));

    // A later GET must not erase the turn that the server never accepted.
    server.row = { ...initialRow, page_index: 6, revision: 4 };
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.loaded).toBe(true));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.reachable).toBe(true));
    await waitFor(() => expect(server.puts).toEqual([{ page_index: 1, revision: 4 }]));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 500)); });

    expect(result.current.pageIndex).toBe(1);
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.settledVersion).toBe(1);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 500)); });
    expect(server.puts).toHaveLength(1);

    // Recovery is deliberate, not a tight retry loop behind the failure.
    act(() => result.current.setPageIndex(2));
    await waitFor(() => expect(server.puts).toEqual([
      { page_index: 1, revision: 4 }, { page_index: 2, revision: 5 },
    ]));
    expect(result.current.pageIndex).toBe(2);
  });

  it("does not retry a pending PUT after a failed focus GET", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const routedFetch = apiFetchMock.getMockImplementation();
    let failedFirstPut = false;
    let putAttempts = 0;
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      if (init?.method === "PUT") {
        putAttempts += 1;
        if (!failedFirstPut) {
          failedFirstPut = true;
          return jsonResponse({ detail: "writer unavailable" }, 503);
        }
      }
      return routedFetch?.(input, init);
    });
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));

    act(() => result.current.setPageIndex(1));
    await waitFor(() => expect(putAttempts).toBe(1));

    server.down = true;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(
      apiFetchMock.mock.calls.filter(([u, i]) => String(u).endsWith("/reading-state") && !i),
    ).toHaveLength(2));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 500)); });
    expect(putAttempts).toBe(1);
    expect(result.current.pageIndex).toBe(1);

    server.down = false;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(server.puts).toEqual([{ page_index: 1, revision: 3 }]));
    expect(putAttempts).toBe(2);
  });

  it("treats a malformed GET row as an unreachable bus", async () => {
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string }) => {
      if (String(input).endsWith("/reading-state") && init?.method !== "PUT") {
        return jsonResponse({ document_id: "other-doc", page_index: 4, revision: 2 });
      }
      return jsonResponse({});
    });
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.loaded).toBe(true));
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.reachable).toBe(false);
    expect(result.current.pageIndex).toBe(0);
  });

  it("treats a malformed PUT response as an unsettled turn", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const routedFetch = apiFetchMock.getMockImplementation();
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      if (init?.method === "PUT") {
        return jsonResponse({ document_id: "doc-1", page_index: "1", revision: 4 });
      }
      return routedFetch?.(input, init);
    });
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    act(() => result.current.setPageIndex(1));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.reachable).toBe(false));
    expect(result.current.pageIndex).toBe(1);
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.settledVersion).toBe(0);
    expect(server.row?.revision).toBe(3);
  });

  it("keeps reading when sessionStorage rejects a position write", async () => {
    const server = busServer({ ...initialRow });
    route(server);
    const setItem = vi.spyOn(window.sessionStorage, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    act(() => result.current.setPageIndex(1));
    expect(result.current.pageIndex).toBe(1);
    await waitFor(() => expect(server.row?.page_index).toBe(1));
    setItem.mockRestore();
  });
});

function AuthReader() {
  const { state, refresh, signOut } = useAuth();
  return <>
    <button onClick={() => void refresh()}>refresh auth</button>
    <button onClick={() => void signOut()}>sign out</button>
    {state.status === "authenticated" && <PositionReader />}
  </>;
}

function PositionReader() {
  const { pageIndex, setPageIndex } = useReadingState("doc-1", 10);
  return <>
    <output data-testid="owner-page">{pageIndex}</output>
    <button onClick={() => setPageIndex(pageIndex + 1)}>turn page</button>
  </>;
}

describe("auth owner transitions", () => {
  it("ignores A's PUT response after sign-out and B sign-in", async () => {
    let signedIn: string | null = "reader-a";
    const heldPut = gate();
    let aPutStarted = false;
    const puts: Array<{ owner: string; revision: number }> = [];
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return signedIn
        ? jsonResponse({ user_id: signedIn, email: null, auth_method: "passkey" })
        : jsonResponse({}, 401);
      if (url.endsWith("/auth/logout")) { signedIn = null; return jsonResponse({}, 204); }
      if (url.endsWith("/reading-state")) {
        if (init?.method !== "PUT") return jsonResponse({}, 404);
        const body: { revision: number } = JSON.parse(init.body ?? "{}");
        const requestOwner = signedIn ?? "none";
        puts.push({ owner: requestOwner, revision: body.revision });
        if (requestOwner === "reader-a") {
          aPutStarted = true;
          await heldPut.promise;
        }
        return jsonResponse({ document_id: "doc-1", page_index: 1, anchor_ref: null, prefs: {}, revision: 1, updated_at: "now" });
      }
      return jsonResponse({});
    });
    render(<AuthProvider><AuthReader /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("0"));
    fireEvent.click(screen.getByText("turn page"));
    await waitFor(() => expect(aPutStarted).toBe(true));
    fireEvent.click(screen.getByText("sign out"));
    await waitFor(() => expect(screen.queryByTestId("owner-page")).toBeNull());
    signedIn = "reader-b";
    fireEvent.click(screen.getByText("refresh auth"));
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("0"));
    heldPut.release();
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("owner-page").textContent).toBe("0");
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(0);
    fireEvent.click(screen.getByText("turn page"));
    await waitFor(() => expect(puts).toEqual([
      { owner: "reader-a", revision: 0 }, { owner: "reader-b", revision: 0 },
    ]));
  });

  it("ignores an old page-turn callback after the owner changes", async () => {
    const server = busServer();
    route(server);
    const { result } = renderHook(() => useReadingState("doc-1", 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.loaded).toBe(true));
    const aTurn = result.current.setPageIndex;
    act(() => setReadingStateOwner("reader-b"));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.loaded).toBe(true));
    act(() => aTurn(8));
    expect(result.current.pageIndex).toBe(0);
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBeNull();
  });

  it("resets a mounted reader when refresh changes directly from A to B", async () => {
    let signedIn = "reader-a";
    apiFetchMock.mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return jsonResponse({ user_id: signedIn, email: null, auth_method: "passkey" });
      if (url.endsWith("/reading-state")) {
        return signedIn === "reader-a"
          ? jsonResponse({ document_id: "doc-1", page_index: 4, anchor_ref: null, prefs: {}, revision: 2, updated_at: "now" })
          : jsonResponse({}, 404);
      }
      return jsonResponse({});
    });
    render(<AuthProvider><AuthReader /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("4"));
    const aKey = positionStorageKey("doc-1");
    signedIn = "reader-b";
    fireEvent.click(screen.getByText("refresh auth"));
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("0"));
    expect(window.sessionStorage.getItem(aKey)).toBe("4");
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBeNull();
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(0);
  });

  it("preserves A's reading state when an identity refresh has a transport failure", async () => {
    let signedIn = "reader-a";
    let failIdentity = false;
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        if (failIdentity) throw new Error("network unavailable");
        return jsonResponse({ user_id: signedIn, email: null, auth_method: "passkey" });
      }
      if (url.endsWith("/auth/logout")) { signedIn = ""; return jsonResponse({}, 204); }
      if (url.endsWith("/reading-state")) {
        if (init?.method === "PUT") return jsonResponse({
          document_id: "doc-1", page_index: 5, anchor_ref: null, prefs: {}, revision: 3, updated_at: "now",
        });
        return jsonResponse({
          document_id: "doc-1", page_index: 4, anchor_ref: null, prefs: {}, revision: 2, updated_at: "now",
        });
      }
      return jsonResponse({});
    });
    render(<AuthProvider><AuthReader /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("4"));
    const aKey = positionStorageKey("doc-1");
    fireEvent.click(screen.getByText("turn page"));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3));
    expect(window.sessionStorage.getItem(aKey)).toBe("5");

    failIdentity = true;
    fireEvent.click(screen.getByText("refresh auth"));
    await waitFor(() => expect(screen.queryByTestId("owner-page")).toBeNull());

    expect(readingPositionOwner()).toBe("reader-a");
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.pageIndex).toBe(5);
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(3);
    expect(window.sessionStorage.getItem(aKey)).toBe("5");
  });

  it("ignores a stale /auth/me response after sign-out and another sign-in", async () => {
    let signedIn: string | null = "reader-a";
    let firstIdentityRequested = false;
    const releaseStaleIdentity = gate();
    const rows = new Map<string, BusRow>();
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        if (!firstIdentityRequested) {
          firstIdentityRequested = true;
          await releaseStaleIdentity.promise;
          return { user_id: "reader-a", email: null, auth_method: "passkey" };
        }
        return signedIn
          ? jsonResponse({ user_id: signedIn, email: null, auth_method: "passkey" })
          : jsonResponse({}, 401);
      }
      if (url.endsWith("/auth/logout")) { signedIn = null; return jsonResponse({}, 204); }
      if (url.endsWith("/reading-state")) {
        const requestOwner = signedIn ?? "none";
        if (init?.method === "PUT") {
          const body: { page_index: number; revision: number } = JSON.parse(init.body ?? "{}");
          const row = rows.get(requestOwner);
          if ((row?.revision ?? 0) !== body.revision) return jsonResponse({}, 409);
          const written: BusRow = {
            page_index: body.page_index, anchor_ref: null, prefs: {},
            revision: body.revision + 1, updated_at: "now",
          };
          rows.set(requestOwner, written);
          return jsonResponse({ document_id: "doc-1", ...written });
        }
        const row = rows.get(requestOwner);
        return row ? jsonResponse({ document_id: "doc-1", ...row }) : jsonResponse({}, 404);
      }
      return jsonResponse({});
    });
    rows.set("reader-b", { page_index: 0, anchor_ref: null, prefs: {}, revision: 0, updated_at: "now" });

    render(<AuthProvider><AuthReader /></AuthProvider>);
    fireEvent.click(screen.getByText("sign out"));
    await waitFor(() => expect(signedIn).toBeNull());

    signedIn = "reader-b";
    fireEvent.click(screen.getByText("refresh auth"));
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("0"));
    const bKey = positionStorageKey("doc-1");
    fireEvent.click(screen.getByText("turn page"));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(1));

    releaseStaleIdentity.release();
    await act(async () => { await releaseStaleIdentity.promise; });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 500)); });

    expect(readingPositionOwner()).toBe("reader-b");
    expect(screen.getByTestId("owner-page").textContent).toBe("1");
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.pageIndex).toBe(1);
    expect(window.sessionStorage.getItem(bKey)).toBe("1");
  });

  it("drops A's held GET and timer, gives B an absent row with revision zero, and isolates reload fallback", async () => {
    let signedIn: string | null = "reader-a";
    const rows = new Map<string, BusRow>();
    const puts: Array<{ owner: string; page: number; revision: number }> = [];
    const heldAGet = gate();
    let holdAGet = false;
    apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return signedIn
        ? jsonResponse({ user_id: signedIn, email: null, auth_method: "passkey" })
        : jsonResponse({}, 401);
      if (url.endsWith("/auth/logout")) { signedIn = null; return jsonResponse({}, 204); }
      if (url.endsWith("/reading-state")) {
        const requestOwner = signedIn ?? "none";
        if (init?.method === "PUT") {
          const body: { page_index: number; revision: number } = JSON.parse(init.body ?? "{}");
          const revision = rows.get(requestOwner)?.revision ?? 0;
          if (body.revision !== revision) return jsonResponse({}, 409);
          puts.push({ owner: requestOwner, page: body.page_index, revision: body.revision });
          const row: BusRow = { page_index: body.page_index, anchor_ref: null, prefs: {}, revision: revision + 1, updated_at: "now" };
          rows.set(requestOwner, row);
          return jsonResponse({ document_id: "doc-1", ...row });
        }
        const snapshot = rows.get(requestOwner);
        if (requestOwner === "reader-a" && holdAGet) await heldAGet.promise;
        return snapshot ? jsonResponse({ document_id: "doc-1", ...snapshot }) : jsonResponse({}, 404);
      }
      return jsonResponse({});
    });
    rows.set("reader-a", { page_index: 4, anchor_ref: null, prefs: {}, revision: 2, updated_at: "now" });
    render(<AuthProvider><AuthReader /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("4"));
    const aKey = positionStorageKey("doc-1");
    holdAGet = true;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(apiFetchMock.mock.calls.filter(([u, i]) => String(u).endsWith("/reading-state") && !i)).toHaveLength(2));
    fireEvent.click(screen.getByText("turn page"));
    expect(screen.getByTestId("owner-page").textContent).toBe("5");
    fireEvent.click(screen.getByText("sign out"));
    await waitFor(() => expect(screen.queryByTestId("owner-page")).toBeNull());
    signedIn = "reader-b";
    fireEvent.click(screen.getByText("refresh auth"));
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("0"));
    heldAGet.release();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 500)); });
    expect(screen.getByTestId("owner-page").textContent).toBe("0");
    expect(puts).toHaveLength(0);
    expect(window.sessionStorage.getItem(aKey)).toBe("5");
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBeNull();
    fireEvent.click(screen.getByText("turn page"));
    await waitFor(() => expect(puts).toEqual([{ owner: "reader-b", page: 1, revision: 0 }]));
    expect(window.sessionStorage.getItem(positionStorageKey("doc-1"))).toBe("1");
    cleanup();
    resetReadingStateBus();
    render(<AuthProvider><AuthReader /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("1"));
  });

  it("loads B's own existing row after a same-tab auth switch", async () => {
    let signedIn = "reader-a";
    apiFetchMock.mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return jsonResponse({ user_id: signedIn, email: null, auth_method: "passkey" });
      if (url.endsWith("/auth/logout")) return jsonResponse({}, 204);
      if (url.endsWith("/reading-state")) return jsonResponse({
        document_id: "doc-1", page_index: signedIn === "reader-a" ? 4 : 7,
        anchor_ref: null, prefs: {}, revision: signedIn === "reader-a" ? 2 : 9, updated_at: "now",
      });
      return jsonResponse({});
    });
    render(<AuthProvider><AuthReader /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("4"));
    fireEvent.click(screen.getByText("sign out"));
    await waitFor(() => expect(screen.queryByTestId("owner-page")).toBeNull());
    signedIn = "reader-b";
    fireEvent.click(screen.getByText("refresh auth"));
    await waitFor(() => expect(screen.getByTestId("owner-page").textContent).toBe("7"));
    expect(useReadingStateBus.getState().byDocument["doc-1"]?.revision).toBe(9);
  });
});
