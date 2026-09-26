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
 *      sessionStorage fallback keeps position working; on recovery the
 *      server value WINS (the substrate-wins merge rule, exercised).
 *   4. CLAMP: a stored position past a shortened book snaps to the last
 *      page on load (usePosition's clamp, now against server-held values).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { WindowHostProvider } from "../../components/windows/windowHostContext";
import { resetReadingStateBus } from "../../hooks/useReadingState";

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
}

function route(server: BusServer) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;

    if (url.endsWith("/reading-state")) {
      if (server.down) return jsonResponse({ detail: "bus down" }, 500);
      if (method === "GET") {
        if (!server.row) return jsonResponse({ detail: "reading_state_not_found" }, 404);
        return jsonResponse({ document_id: "doc-1", ...server.row });
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
        return jsonResponse({ document_id: "doc-1", ...server.row });
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
  it("a failing transport keeps position working from sessionStorage — and on recovery the server value WINS", async () => {
    const server = busServer();
    server.down = true;
    route(server);
    await renderReader();
    await screen.findByText("The opening of the book.");

    // The bus is down: the page turn still works (the sessionStorage
    // fallback layer), and the failed write is marked, never blocking.
    fireEvent.click(screen.getByText("Next →"));
    await screen.findByText("The second page.");
    expect(window.sessionStorage.getItem("antiek.read.pos.doc-1")).toBe("1");
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

    // Recovery: the server has its own authoritative value (written before
    // the outage — page 0). On the focus refetch the SERVER VALUE WINS.
    server.down = false;
    server.row = {
      page_index: 0,
      anchor_ref: null,
      prefs: {},
      revision: 1,
      updated_at: "2026-09-25T12:00:00Z",
    };
    window.dispatchEvent(new Event("focus"));
    await screen.findByText("The opening of the book.");
    expect(screen.queryByText("The second page.")).toBeNull();
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
