/**
 * Reading.citizen.test.tsx — the workstation citizen (reading-global
 * SPR-03), the spec's five proofs:
 *
 *   1. HOP CONTINUITY: in a workstation with a reader tab, turn to page N,
 *      hop to another tab, hop back — page N (the client store); a fresh
 *      mount ("reload") — page N (the server row); the standalone route of
 *      the same document shows page N. ONE position, never two synced
 *      copies.
 *   2. WORKSTATION SWITCH: the outgoing workstation's reader windows tear
 *      down; the incoming one's open reader tabs replay-open at their bus
 *      positions with DEFAULT geometry (geometry asserted absent from every
 *      restored descriptor — never a fabricated stale rect).
 *   3. URL AUDIT: no hop/switch/reload ever puts a workstation/tab
 *      parameter on the URL; a cold /read/:id link renders the surface
 *      with the container restored around it.
 *   4. THE MOUNT MATRIX (the decision-4 assert-not-rebuild proof):
 *      FloatMenu Dialogue + Search render and fire IDENTICALLY in the
 *      standalone route, the reader window, and the reader tab (same
 *      payloads); the §9.0 withheld-selection refusal behaves identically
 *      in all three.
 *   5. POSITION CONFLICT HONESTY: two client instances against the
 *      (stateful) server — last writer wins via revision; the loser
 *      converges on the next refetch. No merge fiction, no error theater.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { DEFAULT_WINDOW_RECT, useWindows } from "../../workspace/windowsStore";
import { WindowHostProvider } from "../../components/windows/windowHostContext";
import { resetReadingStateBus } from "../../hooks/useReadingState";
import { useWorkstationSession } from "../../workspace/workstationSessionStore";
import { readerWindowId } from "../../components/windows/openWindow";

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
  postTypedEventMock: vi.fn((_e: unknown) =>
    Promise.resolve({ event_id: "e-1", action_type: "marginalia.noted" }),
  ),
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

// ── Stateful servers: the reading-state bus + the workstations API ─────────

interface BusServer {
  rows: Record<string, { page_index: number; revision: number }>;
  puts: { documentId: string; page_index: number; revision: number }[];
  conflicts: number;
}

interface WsServer {
  workstations: Record<string, unknown>[];
}

function route(bus: BusServer, ws: WsServer) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;

    if (url.endsWith("/reading-state")) {
      const documentId = url.split("/books/")[1].split("/reading-state")[0];
      if (method === "GET") {
        const row = bus.rows[documentId];
        if (!row) return jsonResponse({ detail: "reading_state_not_found" }, 404);
        return jsonResponse({
          document_id: documentId,
          page_index: row.page_index,
          anchor_ref: null,
          prefs: {},
          revision: row.revision,
          updated_at: "2026-09-25T12:00:00Z",
        });
      }
      if (method === "PUT") {
        bus.puts.push({ documentId, page_index: parsedBody.page_index, revision: parsedBody.revision });
        const row = bus.rows[documentId];
        const current = row?.revision ?? 0;
        if (parsedBody.revision !== current) {
          bus.conflicts += 1;
          return jsonResponse({ detail: "reading_state_stale_revision" }, 409);
        }
        bus.rows[documentId] = { page_index: parsedBody.page_index, revision: current + 1 };
        return jsonResponse({
          document_id: documentId,
          page_index: parsedBody.page_index,
          anchor_ref: null,
          prefs: {},
          revision: current + 1,
          updated_at: "2026-09-25T12:00:00Z",
        });
      }
    }
    if (url.endsWith("/workstations") && method === "GET") {
      return jsonResponse({ workstations: ws.workstations, count: ws.workstations.length });
    }
    if (url.endsWith("/anchors")) {
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
    if (url.includes("/companion") || url.includes("/provenance") || url.endsWith("/evidence")) {
      return jsonResponse({ detail: "book_not_found" }, 404);
    }
    if (url.endsWith("/thought-partner") && method === "POST") {
      return jsonResponse({ text: "a reply", shape: "SYNTHESIS" });
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

function makeWorkstations() {
  return [
    {
      workstation_id: "ws-1",
      name: "The desk",
      color_token: "sun",
      position: 0,
      revision: 1,
      tabs: [
        { tab_id: "tab-read-1", surface_kind: "reader", surface_payload: { documentId: "doc-1" } },
        { tab_id: "tab-research", surface_kind: "route", surface_payload: { route: "/research" } },
      ],
    },
    {
      workstation_id: "ws-2",
      name: "The other desk",
      color_token: "aurora",
      position: 1,
      revision: 1,
      tabs: [
        { tab_id: "tab-read-3", surface_kind: "reader", surface_payload: { documentId: "doc-3" } },
      ],
    },
  ];
}

async function renderStandaloneReader(documentId = "doc-1") {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={[`/read/${documentId}`]}>
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
  window.localStorage.clear();
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
  postTypedEventMock.mockClear();
  searchBlocksMock.mockClear();
  useWorkspace.getState().reset();
  useWindows.getState().reset();
  useWorkstationSession.getState().reset();
  resetReadingStateBus();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ── Proof 1: hop continuity — one position, never two synced copies ────────

describe("hop continuity", () => {
  it("turn to page N, hop away and back — page N; reload — page N; the standalone route agrees", async () => {
    const bus: BusServer = { rows: {}, puts: [], conflicts: 0 };
    route(bus, { workstations: makeWorkstations() });

    // The workstation loads; the reader tab activates (the window opens).
    await act(() => useWorkstationSession.getState().loadFromServer());
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-1"));
    expect(useWindows.getState().order).toEqual([readerWindowId("doc-1")]);

    // Turn to page 2 in the window-mounted reader; the bus write lands.
    const reader = await renderWindowReader("doc-1");
    await screen.findByText("The opening of the book.");
    fireEvent.click(screen.getByText("Next →"));
    await screen.findByText("The second page.");
    await waitFor(() => expect(bus.puts).toHaveLength(1));
    expect(bus.rows["doc-1"]).toEqual({ page_index: 1, revision: 1 });

    // Hop away + back: the tab's surface returns at the bus position (the
    // reader never unmounted; the client store holds the position).
    act(() => useWorkstationSession.getState().hopToTab("ws-1", "tab-research"));
    expect(useWorkstationSession.getState().activeTabIdByWorkstation["ws-1"]).toBe("tab-research");
    act(() => useWorkstationSession.getState().hopToTab("ws-1", "tab-read-1"));
    expect(useWorkstationSession.getState().activeTabIdByWorkstation["ws-1"]).toBe("tab-read-1");
    expect(useWindows.getState().order).toEqual([readerWindowId("doc-1")]); // focused, never duplicated
    expect(useWindows.getState().focusedId).toBe(readerWindowId("doc-1"));
    await screen.findByText("The second page."); // the SAME reader mount, page N

    // RELOAD: a fresh client store — the position comes from the SERVER row.
    reader.unmount();
    resetReadingStateBus();
    await renderWindowReader("doc-1");
    await waitFor(() => screen.findByText("The second page."));

    // The standalone route of the same document agrees (the same row).
    cleanup();
    resetReadingStateBus();
    await renderStandaloneReader("doc-1");
    await waitFor(() => screen.findByText("The second page."));
  });
});

// ── Proof 2: the workstation switch — position survives, geometry does not ─

describe("the workstation switch", () => {
  it("tears down the outgoing windows and replay-opens the incoming reader tabs at bus positions with default rects", async () => {
    const bus: BusServer = { rows: { "doc-3": { page_index: 1, revision: 1 } }, puts: [], conflicts: 0 };
    const wss = makeWorkstations();
    wss[0].tabs.push({
      tab_id: "tab-read-2",
      surface_kind: "reader",
      surface_payload: { documentId: "doc-2" },
    } as never);
    route(bus, { workstations: wss });

    await act(() => useWorkstationSession.getState().loadFromServer());

    // ws-2 first: open its reader tab (doc-3), then switch to ws-1.
    act(() => useWorkstationSession.getState().switchWorkstation("ws-2"));
    act(() => useWorkstationSession.getState().activateTab("ws-2", "tab-read-3"));
    expect(useWindows.getState().order).toEqual([readerWindowId("doc-3")]);
    act(() => useWorkstationSession.getState().switchWorkstation("ws-1"));
    // The teardown closed doc-3's window; its tab stays recorded-open.
    expect(useWindows.getState().order).toEqual([]);

    // In ws-1: open both reader tabs; move doc-1's position on the bus.
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-1"));
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-2"));
    expect(useWindows.getState().order).toEqual([readerWindowId("doc-1"), readerWindowId("doc-2")]);

    // Switch back to ws-2: ws-1's windows tear down; doc-3 replay-opens.
    act(() => useWorkstationSession.getState().switchWorkstation("ws-2"));
    expect(useWindows.getState().order).toEqual([readerWindowId("doc-3")]);
    // DEFAULT geometry — nothing persisted, nothing fabricated: the restored
    // descriptor's rect IS the default rect.
    const desc = useWindows.getState().windows[readerWindowId("doc-3")];
    expect(desc.rect).toEqual({ ...DEFAULT_WINDOW_RECT });

    // And the replayed reader lands at the bus position (page 2 on doc-3).
    getBookMock.mockResolvedValue(makeDetail({ document_id: "doc-3", title: "The Third Book" }));
    getFullTextMock.mockResolvedValue(makeBody({ document_id: "doc-3" }));
    await renderWindowReader("doc-3");
    await waitFor(() => screen.findByText("The second page."));
  });
});

// ── Proof 3: the URL audit + the cold canonical link ───────────────────────

describe("the URL audit", () => {
  it("no hop/switch/reload ever puts a workstation/tab parameter on the URL; a cold /read/:id restores the container around the surface", async () => {
    const bus: BusServer = { rows: {}, puts: [], conflicts: 0 };
    route(bus, { workstations: makeWorkstations() });
    const urlHasContainerParams = () =>
      /[?&](ws|workstation|tab)=/.test(window.location.search);

    await act(() => useWorkstationSession.getState().loadFromServer());
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-1"));
    expect(urlHasContainerParams()).toBe(false);
    act(() => useWorkstationSession.getState().hopToTab("ws-1", "tab-research"));
    act(() => useWorkstationSession.getState().hopToTab("ws-1", "tab-read-1"));
    act(() => useWorkstationSession.getState().switchWorkstation("ws-2"));
    expect(urlHasContainerParams()).toBe(false);

    // A cold canonical /read/:id link: the surface renders AND the
    // container restores around it (the URL-matching tab activates).
    act(() => useWorkstationSession.getState().restoreForUrl("doc-1"));
    expect(useWorkstationSession.getState().activeTabIdByWorkstation["ws-1"]).toBe("tab-read-1");
    await renderStandaloneReader("doc-1");
    await screen.findByText("The opening of the book.");
    expect(urlHasContainerParams()).toBe(false);
    // And reloading restores the last-focused workstation (per-device).
    useWorkstationSession.getState().reset();
    await act(() => useWorkstationSession.getState().loadFromServer());
    expect(useWorkstationSession.getState().focusedWorkstationId).toBe("ws-2");
  });
});

// ── Proof 4: the mount matrix — Dialogue + Search identical in all three ───

describe("the mount matrix (the assert-not-rebuild proof)", () => {
  async function fireSearchIn(container: HTMLElement) {
    await within(container).findByText("The opening of the book.");
    const article = container.querySelector("article")!;
    selectTextIn(article, "The opening of the book.");
    const menu = await within(container).findByRole("menu", { name: /Highlight actions/ });
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Search" }));
    await waitFor(() => expect(searchBlocksMock).toHaveBeenCalled());
  }

  it("Search renders and fires identically in the standalone route, the reader window, and the reader tab", async () => {
    const bus: BusServer = { rows: {}, puts: [], conflicts: 0 };
    route(bus, { workstations: makeWorkstations() });

    // Mount 1: the standalone route.
    const standalone = await renderStandaloneReader("doc-1");
    await fireSearchIn(standalone.container);
    // Mount 2: the reader window.
    const windowed = await renderWindowReader("doc-1");
    await fireSearchIn(windowed.container);
    // Mount 3: the reader TAB (activated via the session store, rendered as
    // the same BookReader).
    await act(() => useWorkstationSession.getState().loadFromServer());
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-1"));
    const tabbed = await renderWindowReader("doc-1");
    await fireSearchIn(tabbed.container);

    // Three mounts, THREE identical calls — same query, same path.
    expect(searchBlocksMock).toHaveBeenCalledTimes(3);
    const queries = searchBlocksMock.mock.calls.map(([q]) => q);
    expect(new Set(queries).size).toBe(1);
    expect(queries[0]).toBe("The opening of the book.");
  });

  it("Dialogue renders and fires identically in all three mounts", async () => {
    const bus: BusServer = { rows: {}, puts: [], conflicts: 0 };
    route(bus, { workstations: makeWorkstations() });

    const dialogueCalls: unknown[] = [];
    async function fireDialogueIn(container: HTMLElement) {
      await within(container).findByText("The opening of the book.");
      const article = container.querySelector("article")!;
      selectTextIn(article, "The opening of the book.");
      const menu = await within(container).findByRole("menu", { name: /Highlight actions/ });
      fireEvent.click(within(menu).getByRole("menuitem", { name: "Dialogue" }));
      const input = await within(container).findByRole("textbox");
      fireEvent.change(input, { target: { value: "what does this mean?" } });
      fireEvent.click(within(container).getByRole("button", { name: "Ask" }));
      await waitFor(() =>
        expect(
          apiFetchMock.mock.calls.filter(
            ([u]) => String(u).endsWith("/thought-partner"),
          ).length,
        ).toBeGreaterThan(dialogueCalls.length),
      );
      const call = apiFetchMock.mock.calls
        .filter(([u]) => String(u).endsWith("/thought-partner"))
        .at(-1);
      dialogueCalls.push(JSON.parse(String(call?.[1]?.body)));
    }

    const standalone = await renderStandaloneReader("doc-1");
    await fireDialogueIn(standalone.container);
    const windowed = await renderWindowReader("doc-1");
    await fireDialogueIn(windowed.container);
    await act(() => useWorkstationSession.getState().loadFromServer());
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-1"));
    const tabbed = await renderWindowReader("doc-1");
    await fireDialogueIn(tabbed.container);

    expect(dialogueCalls).toHaveLength(3);
    // The same prompt shape in all three (the selection + the follow-up).
    const prompts = dialogueCalls.map((c) => (c as { prompt: string }).prompt);
    expect(new Set(prompts).size).toBe(1);
    expect(prompts[0]).toContain("The opening of the book.");
    expect(prompts[0]).toContain("what does this mean?");
  });

  it("the §9.0 withheld-selection refusal behaves identically in all three mounts", async () => {
    const bus: BusServer = { rows: {}, puts: [], conflicts: 0 };
    route(bus, { workstations: makeWorkstations() });
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: "A short gate-served preview.",
        servability: "gated_metadata_only",
        reason: "gated_metadata_only",
      }),
    );

    async function refuseSearchIn(container: HTMLElement) {
      const para = await within(container).findByText(/A short gate-served preview\./);
      selectTextIn(para, "A short gate-served preview.");
      const menu = await within(container).findByRole("menu", { name: /Highlight actions/ });
      fireEvent.click(within(menu).getByRole("menuitem", { name: "Search" }));
      await within(container).findByText(/includes a restricted source/);
    }

    const standalone = await renderStandaloneReader("doc-1");
    await refuseSearchIn(standalone.container);
    const windowed = await renderWindowReader("doc-1");
    await refuseSearchIn(windowed.container);
    await act(() => useWorkstationSession.getState().loadFromServer());
    act(() => useWorkstationSession.getState().activateTab("ws-1", "tab-read-1"));
    const tabbed = await renderWindowReader("doc-1");
    await refuseSearchIn(tabbed.container);

    // The withheld body NEVER left the client — in ANY mount.
    expect(searchBlocksMock).not.toHaveBeenCalled();
  });
});

// ── Proof 5: position conflict honesty ─────────────────────────────────────

describe("position conflict honesty", () => {
  it("the loser of a revision conflict converges on the server value — no merge fiction, no error theater", async () => {
    const bus: BusServer = { rows: { "doc-1": { page_index: 0, revision: 1 } }, puts: [], conflicts: 0 };
    route(bus, { workstations: makeWorkstations() });
    // A three-page body, so the loser's convergence is OBSERVABLE (its local
    // turn target differs from the server's value).
    getFullTextMock.mockResolvedValue(
      makeBody({
        full_text:
          "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.\n\n## Page 3\n\nThe third page.",
      }),
    );

    // Instance A loads (server: page 0, revision 1).
    await renderStandaloneReader("doc-1");
    await screen.findByText("The opening of the book.");

    // Instance B (the other "device") moves to page 3 — the server row
    // advances past A's known revision.
    bus.rows["doc-1"] = { page_index: 2, revision: 2 };

    // A turns to page 2 at its STALE revision → the write 409s → A
    // converges on the refetch: the server says page 3, so A snaps PAST its
    // own turn (the local write lost — last writer wins).
    fireEvent.click(screen.getByText("Next →"));
    await screen.findByText("The second page."); // A's local turn shows first
    await waitFor(() => expect(bus.puts).toHaveLength(1));
    await waitFor(() => expect(bus.conflicts).toBe(1));
    await waitFor(() => screen.findByText("The third page.")); // the SERVER's value wins
    expect(screen.queryByText("The second page.")).toBeNull();
    // No error theater: nothing error-shaped rendered for the conflict.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
