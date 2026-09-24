/**
 * Reading.spawnFlows.test.tsx — island SPR-03 spawn-flow proofs.
 *
 *   - FREE-INQUIRY ("Research from here"): pin the current page's lead
 *     passage FIRST (source=pin) → spin seeded with the pinned passage →
 *     write-back → the island emerges — never a navigation away;
 *   - the GATED refusal: an owner-readable book whose anchor-map is
 *     withheld can't anchor a passage — NO pin, NO spawn, and the passage
 *     text appears in NO outbound call (the §9.0 rule);
 *   - the FAILURE MATRIX: a pin 422 (ambiguous passage) spawns nothing and
 *     leaves no anchor; a spawn failure leaves the lawful pinned highlight
 *     with an honest error and a RETRY reuses the SAME anchor (no duplicate
 *     pin), then links and the island emerges.
 *
 * The harness mirrors Reading.anchors.test.tsx: the stateful transport mock
 * with a memory (seedServer), the global fetch stub for lib/api-internal
 * anchor clients, and a mounted LemonToastViewport so the honest messages
 * are asserted where the operator actually sees them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import type { BookAnchor } from "../../lib/api";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { LemonToastViewport } from "../../components/lemon/LemonToast";

const {
  getBookMock,
  getFullTextMock,
  listBooksMock,
  spinResearchMock,
  navigateMock,
  useInvestigationMock,
  postTypedEventMock,
  searchBlocksMock,
  startInvestigationMock,
  apiFetchMock,
} = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  spinResearchMock: vi.fn(),
  navigateMock: vi.fn(),
  useInvestigationMock: vi.fn(),
  postTypedEventMock: vi.fn((_e: unknown) =>
    Promise.resolve({ event_id: "ev-1", action_type: "marginalia.noted" }),
  ),
  searchBlocksMock: vi.fn((_q: string) => Promise.resolve({ count: 0, hits: [] })),
  startInvestigationMock: vi.fn((_r: unknown) =>
    Promise.resolve({ investigation_id: "child-1", status: "in_progress", start_event_id: "ev-s" }),
  ),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
    spinResearch: spinResearchMock,
  };
});

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (e: unknown) => postTypedEventMock(e),
    searchBlocks: (q: string) => searchBlocksMock(q),
    startInvestigation: (r: unknown) => startInvestigationMock(r),
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

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

// ── A tiny stateful anchor server (the transport mock with a memory) ──────

interface AnchorServer {
  rows: BookAnchor[];
  calls: { method: string; url: string; body?: unknown }[];
}

function anchorRow(over: Partial<BookAnchor> = {}): BookAnchor {
  return {
    anchor_id: "a-1",
    document_id: "doc-1",
    anchor: {
      normalization: "unicode-nfc-v1",
      node_id: "c-1",
      node_text_sha256: "h".repeat(64),
      start_scalar: 0,
      end_scalar: 7,
      quote: "The ope",
      prefix: "",
      suffix: "ning of the book.",
    },
    servable_at_pin: true,
    selection_text_sha256: "s".repeat(64),
    page_index_hint: 0,
    source: "pin",
    status: "active",
    exact_valid: true,
    investigation_id: null,
    created_at: "2026-09-25T10:00:00Z",
    updated_at: "2026-09-25T10:00:00Z",
    ...over,
  };
}

interface SeedOptions {
  /** When set, POST /anchors fails with this status (the pin-422 case). */
  pinStatus?: number;
  /** When set, the OWNER anchor-map fails with this status (the gated case). */
  ownerMapStatus?: number;
}

function seedServer(rows: BookAnchor[], opts: SeedOptions = {}): AnchorServer {
  const server: AnchorServer = { rows: [...rows], calls: [] };
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    server.calls.push({ method, url, body: parsedBody });

    if (url.endsWith("/anchors") && method === "GET") {
      // Fresh array + rows each time (production JSON is never a shared
      // reference — a shared ref would make setState bail on identity).
      return jsonResponse({
        document_id: "doc-1",
        anchors: server.rows.map((r) => ({ ...r, anchor: { ...r.anchor } })),
        count: server.rows.length,
      });
    }
    if (url.endsWith("/anchors") && method === "POST") {
      if (opts.pinStatus) {
        return jsonResponse(
          { detail: "anchor_resolution_ambiguous: the passage pins more than once" },
          opts.pinStatus,
        );
      }
      const row = anchorRow({
        anchor_id: `ahl-${server.rows.length + 1}`,
        source: parsedBody?.source ?? "pin",
        anchor: parsedBody?.quote
          ? { ...anchorRow().anchor, quote: parsedBody.quote, start_scalar: 0, end_scalar: parsedBody.quote.length }
          : { ...anchorRow().anchor, quote: "", prefix: "", suffix: "" },
        servable_at_pin: Boolean(parsedBody?.quote),
      });
      server.rows.push(row);
      return jsonResponse(row, 201);
    }
    if (url.includes("/anchors/") && method === "PATCH") {
      const id = url.split("/anchors/")[1];
      const row = server.rows.find((r) => r.anchor_id === id);
      if (!row) return jsonResponse({ detail: "anchor_not_found" }, 404);
      if (row.investigation_id && row.investigation_id !== parsedBody?.investigation_id) {
        return jsonResponse({ detail: "anchor_already_linked" }, 409);
      }
      row.investigation_id = parsedBody?.investigation_id ?? row.investigation_id;
      return jsonResponse(row);
    }
    if (url.includes("/investigations")) {
      // ReadingCompanion's useInvestigationList reads this through lib/api's
      // internal binding (the global fetch stub) — an empty, well-formed list.
      return jsonResponse({ count: 0, investigations: [] });
    }
    if (url.endsWith("/anchor-map/owner")) {
      if (opts.ownerMapStatus) {
        return jsonResponse({ detail: "anchor_map_owner_forbidden" }, opts.ownerMapStatus);
      }
    }
    if (url.endsWith("/anchor-map")) {
      return jsonResponse({
        document_id: "doc-1",
        chunks: [
          {
            chunk_id: "c-1",
            section_path: "Page 1",
            body_start: 11,
            body_end: 33,
            node_text_sha256: "h".repeat(64),
          },
        ],
        complete: true,
      });
    }
    return jsonResponse({ text: "reply" });
  });
  return server;
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

async function renderReader(initialEntry = "/read/doc-1") {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
      <LemonToastViewport />
    </MemoryRouter>,
  );
}

function selectTextIn(scope: HTMLElement, text: string) {
  const node = scope.firstChild as Node | null;
  const range = document.createRange();
  if (node) range.selectNodeContents(node);
  else range.selectNodeContents(scope);
  range.getBoundingClientRect = () =>
    ({ top: 200, left: 100, width: 80, height: 18, right: 180, bottom: 218, x: 100, y: 200, toJSON: () => ({}) }) as DOMRect;
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 1,
    getRangeAt: () => range,
    toString: () => text,
    removeAllRanges: () => {},
  } as unknown as Selection);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

beforeEach(() => {
  window.sessionStorage.clear();
  // The anchor client functions live INSIDE lib/api and keep their
  // module-local apiFetch binding — so apiFetch (real) must reach the same
  // mock: stub the global fetch apiFetch delegates to. FloatMenuActions'
  // apiFetch is the mocked one anyway — one boundary, one memory.
  vi.stubGlobal("fetch", apiFetchMock);
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
  spinResearchMock.mockReset().mockResolvedValue({
    investigation_id: "inv-spawned",
    document_id: "doc-1",
    page_index: 0,
    gated: false,
    servability: "public_domain",
    seed_preview: "seed",
    artifact_path: null,
    twin_notes_path: null,
  });
  navigateMock.mockReset();
  postTypedEventMock.mockClear();
  searchBlocksMock.mockClear();
  startInvestigationMock.mockClear();
  apiFetchMock.mockReset();
  useWorkspace.getState().reset();
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
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The island's thread projection, live (SPR-01's path, end-to-end). */
function liveThreadProjection() {
  useInvestigationMock.mockImplementation((id: string) => ({
    id,
    status: "in_progress",
    question: "the spawned question",
    events: [],
    terminalPayload: null,
    costTotal: 0.42,
    completedAt: null,
    streamStatus: "open" as const,
    reconnects: 0,
    sourcePolicy: [],
  }));
}

// ── Proof 1: the free-inquiry spawn flow ───────────────────────────────────

describe("the free-inquiry spawn flow (island SPR-03)", () => {
  it("Research from here pins the page's lead passage, spins seeded with it, links — and the island emerges with NO navigation", async () => {
    liveThreadProjection();
    const server = seedServer([]);
    await renderReader();
    await screen.findByText("The opening of the book.");
    // The free-inquiry anchors the page's lead passage through the
    // anchor-map — wait for the manifest to land before clicking.
    await waitFor(() =>
      expect(
        server.calls.some((c) => c.method === "GET" && c.url.endsWith("/anchor-map")),
      ).toBe(true),
    );

    fireEvent.click(screen.getByRole("button", { name: "Research from here" }));
    await waitFor(() => expect(spinResearchMock).toHaveBeenCalledTimes(1));

    // The pin came FIRST (source=pin, the page's lead passage as the quote)
    // and the spin's seed IS the pinned passage.
    const posts = server.calls.filter(
      (c) => c.method === "POST" && c.url.endsWith("/anchors"),
    );
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({
      source: "pin",
      quote: "The opening of the book.",
    });
    expect(spinResearchMock).toHaveBeenCalledWith(
      "doc-1",
      0,
      "The opening of the book.",
    );
    // The write-back linked the spawned thread onto the anchor.
    const patches = server.calls.filter((c) => c.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toEqual({ investigation_id: "inv-spawned" });
    expect(server.rows[0].investigation_id).toBe("inv-spawned");
    // The reader did NOT navigate away — the island emerges instead.
    expect(navigateMock).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(document.querySelector('[data-island-id="ahl-1"]')).toBeTruthy(),
    );
    expect(
      document.querySelector('[data-island-id="ahl-1"]')!.getAttribute("data-island-status"),
    ).toBe("live");
  });
});

// ── Proof 2: the gated refusal (§9.0 — no anchor, no island, no leak) ─────

describe("the gated free-inquiry refusal", () => {
  it("an owner-readable book with a withheld anchor-map refuses: NO pin, NO spawn, and the passage text leaves in NO call", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: true,
        servability: "gated_metadata_only",
        reason: "owner_personal_reading",
      }),
    );
    // The owner anchor-map is withheld (403) — no passage can anchor.
    const server = seedServer([], { ownerMapStatus: 403 });
    await renderReader();
    await screen.findByText("The opening of the book.");

    fireEvent.click(screen.getByRole("button", { name: "Research from here" }));

    // The honest refusal surfaces where the operator sees it.
    await screen.findByText(/Couldn't anchor this passage/);
    // NO pin, NO spin, NO write-back — never an anchorless island.
    expect(
      server.calls.filter((c) => c.method === "POST" && c.url.endsWith("/anchors")),
    ).toHaveLength(0);
    expect(spinResearchMock).not.toHaveBeenCalled();
    expect(server.calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    expect(server.rows).toHaveLength(0);
    expect(document.querySelector("[data-island-id]")).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
    // The withheld passage text appeared in NO outbound call's payload.
    expect(JSON.stringify(server.calls)).not.toContain("The opening of the book");
  });
});

// ── Proof 3: the failure matrix ────────────────────────────────────────────

describe("the spawn-flow failure matrix", () => {
  it("a pin 422 (an ambiguous passage) spawns NOTHING — no thread, no island, no anchor", async () => {
    const server = seedServer([], { pinStatus: 422 });
    await renderReader();
    await screen.findByText("The opening of the book.");
    const article = document.querySelector("article")!;

    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));

    // The pin failure is the honest error the operator sees — and NO thread
    // is spawned (never an anchorless island).
    await screen.findByText(/Couldn't anchor this passage/);
    expect(spinResearchMock).not.toHaveBeenCalled();
    expect(server.calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    expect(server.rows).toHaveLength(0);
    expect(document.querySelector("[data-island-id]")).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("a failed spawn leaves the pinned highlight with an honest error — and a RETRY reuses the SAME anchor", async () => {
    liveThreadProjection();
    spinResearchMock.mockRejectedValueOnce(new Error("capacity exhausted"));
    const server = seedServer([]);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const article = document.querySelector("article")!;

    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    await waitFor(() => expect(spinResearchMock).toHaveBeenCalledTimes(1));

    // The honest error; the lawful pinned highlight REMAINS (no link, no
    // island yet).
    await screen.findByText(/The research didn't start/);
    await screen.findByText(/Your highlight is still pinned/);
    expect(server.rows).toHaveLength(1);
    expect(server.rows[0].investigation_id).toBeNull();
    expect(server.calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    expect(document.querySelector("[data-island-id]")).toBeNull();

    // The retry: the dedupe-by-location REUSES the same anchor (the pin is
    // skipped — asserted by request count), the spin succeeds, the link
    // lands, and the island emerges.
    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    await waitFor(() => expect(spinResearchMock).toHaveBeenCalledTimes(2));
    expect(
      server.calls.filter((c) => c.method === "POST" && c.url.endsWith("/anchors")),
    ).toHaveLength(1); // no duplicate pin
    expect(server.rows).toHaveLength(1);
    await waitFor(() =>
      expect(server.rows[0].investigation_id).toBe("inv-spawned"),
    );
    await waitFor(() =>
      expect(document.querySelector('[data-island-id="ahl-1"]')).toBeTruthy(),
    );
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
