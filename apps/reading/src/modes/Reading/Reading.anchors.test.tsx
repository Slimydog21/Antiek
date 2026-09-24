/**
 * Reading.anchors.test.tsx — anchor-first SPR-02 reader proofs.
 *
 *   - seeded anchors paint decorations with stable data-anchor-id at the
 *     correct passage on the correct page — in the standalone route AND the
 *     window-mounted reader (one implementation, both mounts);
 *   - a drifted anchor renders the dashed/low-emphasis treatment; an
 *     orphaned one renders nothing in the body and one honest list row
 *     (with delete as the only removal);
 *   - the marks are INLINE (part of the text flow — they cannot strand the
 *     way the old raw-rect menu could), and a page round-trip returns them;
 *   - pin → reload → the same decoration returns (the real useAnchors hook
 *     over a mocked-but-stateful transport);
 *   - every FloatMenu action auto-pins exactly once; Deep-research pins,
 *     spins, and writes the spawned thread onto the anchor (first link
 *     wins — a second spawn leaves the payload unchanged);
 *   - the HONEST GAP is closed: the in-book NOTE now chains a REAL chunk id
 *     resolved via the anchor-map (was null by design).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import type { BookAnchor } from "../../lib/api";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { WindowHostProvider } from "../../components/windows/windowHostContext";

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
    created_at: "2026-09-24T10:00:00Z",
    updated_at: "2026-09-24T10:00:00Z",
    ...over,
  };
}

function seedServer(rows: BookAnchor[]): AnchorServer {
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
      if (row) row.investigation_id = parsedBody?.investigation_id ?? null;
      return jsonResponse(row ?? {});
    }
    if (url.includes("/anchors/") && method === "DELETE") {
      const id = url.split("/anchors/")[1];
      server.rows = server.rows.filter((r) => r.anchor_id !== id);
      return new Response(null, { status: 204 });
    }
    if (url.includes("/investigations")) {
      // ReadingCompanion's useInvestigationList reads this through lib/api's
      // internal binding (the global fetch stub) — an empty, well-formed list.
      return jsonResponse({ count: 0, investigations: [] });
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
    </MemoryRouter>,
  );
}

async function renderWindowReader(documentId: string) {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/research"]}>
      <WindowHostProvider value={true}>
        <BookReader documentId={documentId} />
      </WindowHostProvider>
    </MemoryRouter>,
  );
}

function clearSelection() {
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 0,
    getRangeAt: () => {
      throw new Error("no range");
    },
    toString: () => "",
    removeAllRanges: () => {},
  } as unknown as Selection);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
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

// ── Proof 2: decorations in both mounts ────────────────────────────────────

describe("seeded anchors paint decorations in BOTH mounts", () => {
  it("standalone route: an active anchor paints data-anchor-id at the correct passage on the correct page", async () => {
    seedServer([anchorRow()]);
    await renderReader();
    const mark = await screen.findByText("The ope");
    expect(mark.getAttribute("data-anchor-id")).toBe("a-1");
    expect(mark.getAttribute("data-anchor-treatment")).toBe("active");
    expect(mark.textContent).toBe("The ope");
    expect(mark.className).toContain("underline");
    // The mark is INLINE inside the page paragraph (not a floating overlay).
    expect(mark.closest("article")).toBeTruthy();
    expect(mark.closest("p")).toBeTruthy();
  });

  it("window-mounted reader: the same decoration paints (one implementation, both mounts)", async () => {
    seedServer([anchorRow()]);
    await renderWindowReader("doc-1");
    const mark = await screen.findByText("The ope");
    expect(mark.getAttribute("data-anchor-id")).toBe("a-1");
    expect(mark.getAttribute("data-anchor-treatment")).toBe("active");
  });

  it("a page round-trip returns the same mark (content-derived, never pixel-stranded)", async () => {
    seedServer([anchorRow()]);
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(screen.getByText("Next →"));
    await screen.findByText("The second page.");
    expect(screen.queryByText("The ope")).toBeNull();
    fireEvent.click(screen.getByText("← Previous"));
    const mark = await screen.findByText("The ope");
    expect(mark.getAttribute("data-anchor-id")).toBe("a-1");
  });
});

// ── Proof 4: drifted and orphaned renderings ───────────────────────────────

describe("drifted and orphaned renderings", () => {
  it("a drifted anchor renders the dashed/low-emphasis treatment with the honest moved affordance", async () => {
    seedServer([anchorRow({ anchor_id: "a-drift", status: "drifted" })]);
    await renderReader();
    const mark = await screen.findByText("The ope");
    expect(mark.getAttribute("data-anchor-treatment")).toBe("drifted");
    expect(mark.className).toContain("decoration-dashed");
    expect(mark.className).toContain("opacity-70");
    expect(mark.getAttribute("title")).toContain("Moved");
  });

  it("an orphaned anchor renders NOTHING in the body and one honest list row (delete removes it)", async () => {
    seedServer([anchorRow({ anchor_id: "a-gone", status: "orphaned", page_index_hint: 2 })]);
    await renderReader();
    await screen.findByText("The opening of the book.");
    expect(document.querySelector("[data-anchor-id]")).toBeNull();
    const row = document.querySelector('[data-orphaned-anchor="a-gone"]')!;
    expect(row).toBeTruthy();
    expect(row.textContent).toContain("Page 3");
    expect(row.textContent).toContain("text no longer found");
    fireEvent.click(row.querySelector("button")!);
    await waitFor(() =>
      expect(document.querySelector('[data-orphaned-anchor="a-gone"]')).toBeNull(),
    );
  });
});

// ── Proof 5: pin → reload → the decoration returns ─────────────────────────

describe("pin → reload → the same decoration returns", () => {
  it("pinning via the Pin button persists and re-paints after a reload", async () => {
    const server = seedServer([]);
    const first = await renderReader();
    await screen.findByText("The opening of the book.");
    selectTextIn(document.querySelector("article")!, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Pin" }));
    await waitFor(() =>
      expect(server.calls.some((c) => c.method === "POST" && c.url.endsWith("/anchors"))).toBe(true),
    );
    expect(server.rows).toHaveLength(1);
    expect(server.rows[0].source).toBe("pin");
    // The decoration paints from the refetch.
    const mark = await screen.findByText("The open");
    expect(mark.getAttribute("data-anchor-id")).toBe("ahl-1");
    first.unmount();

    // Reload (fresh mount): the persisted anchor paints again.
    await renderReader();
    const again = await screen.findByText("The open");
    expect(again.getAttribute("data-anchor-id")).toBe("ahl-1");
  });
});

// ── Proof 1 (reader level): every action auto-pins exactly once ────────────

describe("every FloatMenu action auto-pins exactly once (reader host)", () => {
  it("Note, Dialogue, Search fire one pin each with their source and the quote context", async () => {
    const server = seedServer([]);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const article = document.querySelector("article")!;

    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Note" }));
    await waitFor(() => expect(server.calls.filter((c) => c.method === "POST")).toHaveLength(1));
    const posts = () => server.calls.filter((c) => c.method === "POST");
    expect(posts()[0].body).toMatchObject({ source: "floatmenu_note", quote: "The open" });

    clearSelection();
    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Dialogue" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1].body).toMatchObject({ source: "floatmenu_dialogue" });

    clearSelection();
    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Search" }));
    await waitFor(() => expect(posts()).toHaveLength(3));
    expect(posts()[2].body).toMatchObject({ source: "floatmenu_search" });
  });
});

// ── Proof 6: the Deep-research spawn write-back (first link wins) ──────────

describe("the Deep-research spawn write-back (SPR-04 tail)", () => {
  it("pins, spins, writes the spawned thread onto the anchor — and a second spawn does NOT overwrite", async () => {
    const server = seedServer([]);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const article = document.querySelector("article")!;

    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    await waitFor(() => expect(spinResearchMock).toHaveBeenCalledTimes(1));

    // The pin POST preceded the spin; the PATCH link followed it.
    const posts = server.calls.filter((c) => c.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ source: "floatmenu_deep_research" });
    const patches = server.calls.filter((c) => c.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toEqual({ investigation_id: "inv-spawned" });
    expect(server.rows[0].investigation_id).toBe("inv-spawned");
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-spawned");

    // A second spawn from another highlight: the server keeps the first link.
    const firstLink = server.rows[0].investigation_id;
    spinResearchMock.mockResolvedValueOnce({
      investigation_id: "inv-second",
      document_id: "doc-1",
      page_index: 0,
      gated: false,
      servability: "public_domain",
      seed_preview: "seed",
      artifact_path: null,
      twin_notes_path: null,
    });
    selectTextIn(article, "opening of");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    await waitFor(() => expect(spinResearchMock).toHaveBeenCalledTimes(2));
    // The second pin is a NEW anchor; the FIRST anchor's link is unchanged.
    expect(server.rows[0].investigation_id).toBe(firstLink);
    expect(server.rows[1].investigation_id).toBe("inv-second");
  });
});

// ── The HONEST GAP closure: a real chunk id on the in-book NOTE ────────────

describe("the HONEST GAP closure", () => {
  it("the in-book NOTE now chains a REAL chunk id resolved via the anchor-map (was null by design)", async () => {
    seedServer([]);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const article = document.querySelector("article")!;
    selectTextIn(article, "The open");
    fireEvent.click(screen.getByRole("menuitem", { name: "Note" }));
    const textarea = await screen.findByPlaceholderText(/Type a note/);
    fireEvent.change(textarea, { target: { value: "remember this" } });
    fireEvent.click(screen.getByText("Save note"));
    await waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    const payload = JSON.stringify(postTypedEventMock.mock.calls[0][0]);
    expect(payload).toContain("c-1");
  });
});
