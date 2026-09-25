/**
 * Reading.reformat.test.tsx — the reformat flow (reformat-provenance
 * SPR-02), the spec's five proofs:
 *
 *   1. The island affordance: the prompt rides runSpawnFlow's pin→spin→link
 *      discipline (the island's anchor is NOT re-pinned; the reformat POST
 *      payload asserted; the link 409-keeps honestly) and the engagement
 *      STAYS in the card (no navigation);
 *   2. ask-to-open: completion asks; CONFIRM opens exactly ONE reader
 *      window on the derived document with the reformat origin; DECLINE
 *      opens nothing;
 *   3. the review surface: honesty header + per-bite class markers + the
 *      trace jump opening the SOURCE at the passage (the anchor payload on
 *      the open call) + the honest null-source line;
 *   4. merge/fork wiring: a 404 from the unit-5 contract paths degrades to
 *      the named pending state (never a fake success); a reachable fork API
 *      receives the generation record's refs on the request body;
 *   5. the honesty header renders on the derived document; the original
 *      shows no marker.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import type { BookAnchor } from "../../lib/api";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { useWindows } from "../../workspace/windowsStore";
import { resetReadingStateBus } from "../../hooks/useReadingState";
import { readerWindowId } from "../../components/windows/openWindow";

const {
  getBookMock,
  getFullTextMock,
  listBooksMock,
  navigateMock,
  useInvestigationMock,
  postTypedEventMock,
  searchBlocksMock,
  apiFetchMock,
} = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  navigateMock: vi.fn(),
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

function islandAnchor(): BookAnchor {
  return {
    anchor_id: "a-island",
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
    source: "floatmenu_deep_research",
    status: "active",
    exact_valid: true,
    investigation_id: "inv-thread",
    created_at: "2026-09-25T10:00:00Z",
    updated_at: "2026-09-25T10:00:00Z",
  };
}

const REFORMAT_RESULT = {
  generation_id: "gen-1",
  derived_document_id: "drv-x1",
  thread_id: "reformat:gen-1",
  bite_count: 3,
  contribution_classes: ["author_verbatim", "llm_compressed", "llm_expanded"],
  mostly_generated: false,
  reclassed_verbatim: 0,
  null_source_share: 0,
};

const PROVENANCE = {
  document_id: "drv-x1",
  generation: {
    generation_id: "gen-1",
    source_document_id: "doc-1",
    source_title: "A Servable Book",
    prompt: "the 20-minute version",
    model: "fixture-model",
    params: { mode: "time_window" },
    mostly_generated: false,
    created_at: "2026-09-25T12:00:00Z",
  },
  bites: [
    {
      bite_id: "bite-0",
      ordinal: 0,
      contribution_class: "author_verbatim",
      source_refs: [{ node_id: "c-1", start_scalar: 0, end_scalar: 7 }],
      source_page_hints: [0],
      investigation_id: null,
      byte_verified: true,
    },
    {
      bite_id: "bite-1",
      ordinal: 1,
      contribution_class: "llm_compressed",
      source_refs: [{ node_id: "c-1", start_scalar: 8, end_scalar: 30 }],
      source_page_hints: [1],
      investigation_id: null,
      byte_verified: false,
    },
    {
      bite_id: "bite-2",
      ordinal: 2,
      contribution_class: "llm_expanded",
      source_refs: null,
      source_page_hints: [],
      investigation_id: null,
      byte_verified: false,
    },
  ],
};

interface Server {
  posts: { url: string; body: Record<string, unknown> }[];
  patches: { url: string; body: Record<string, unknown> }[];
  forkReachable: boolean;
}

function route(server: Server) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    if (method === "POST") server.posts.push({ url, body: parsedBody });
    if (method === "PATCH") server.patches.push({ url, body: parsedBody });

    if (url.endsWith("/reformats") && method === "POST") {
      return jsonResponse(REFORMAT_RESULT, 201);
    }
    if (url.includes("/provenance")) {
      // The derived document carries a record; the ORIGINAL 404s (no marker).
      if (url.includes("/documents/drv-")) return jsonResponse(PROVENANCE);
      return jsonResponse({ detail: "provenance_not_found" }, 404);
    }
    if (url.endsWith("/forks") && method === "POST") {
      if (!server.forkReachable) {
        return jsonResponse({ detail: "fork API pending" }, 404);
      }
      return jsonResponse({ fork_id: "fork-1" }, 201);
    }
    if (url.includes("/merge") && method === "POST") {
      return jsonResponse({ detail: "merge API pending" }, 404);
    }
    if (url.endsWith("/anchors") && method === "GET") {
      const a = islandAnchor();
      return jsonResponse({ document_id: "doc-1", anchors: [{ ...a, anchor: { ...a.anchor } }], count: 1 });
    }
    if (url.includes("/anchors/") && method === "PATCH") {
      // First link wins — the island's thread holds the anchor already.
      return jsonResponse({ detail: "anchor_already_linked" }, 409);
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
    if (url.includes("/companion")) {
      return jsonResponse({ detail: "book_not_found" }, 404);
    }
    if (url.endsWith("/reading-state")) {
      return jsonResponse({ detail: "reading_state_not_found" }, 404);
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

async function renderReader(documentId = "doc-1") {
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

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.removeItem("antiek.island.hidden");
  vi.stubGlobal("fetch", apiFetchMock);
  apiFetchMock.mockReset();
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
  navigateMock.mockReset();
  useInvestigationMock.mockReset().mockReturnValue({
    id: "inv-thread",
    status: "in_progress",
    question: "the island's question",
    events: [],
    terminalPayload: null,
    costTotal: 0.42,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
  });
  useWorkspace.getState().reset();
  useWindows.getState().reset();
  resetReadingStateBus();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ── Proofs 1 + 2: the island affordance + ask-to-open ──────────────────────

describe("the island reformat affordance + ask-to-open", () => {
  it("the prompt rides the pin→spin→link discipline; the engagement stays in the card (no navigation); completion asks, confirm opens ONE reader window with the reformat origin, decline opens nothing", async () => {
    const server: Server = { posts: [], patches: [], forkReachable: false };
    route(server);
    await renderReader();
    await screen.findByText("The ope");

    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    fireEvent.click(await screen.findByRole("button", { name: "Reformat this" }));
    const composer = document.querySelector("[data-reformat-flow]")!;
    expect(composer).toBeTruthy();
    fireEvent.change(screen.getByLabelText("What should the reformat do?"), {
      target: { value: "the 20-minute version" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reformat" }));

    // The spin: exactly ONE reformat POST with the prompt + mode.
    await waitFor(() =>
      expect(server.posts.some((c) => c.url.includes("/reformats"))).toBe(true),
    );
    const reformatPost = server.posts.find((c) => c.url.includes("/reformats"))!;
    expect(reformatPost.body.prompt).toBe("the 20-minute version");
    expect(reformatPost.body.mode).toBe("time_window");
    // The pin step did NOT re-pin (the island's anchor exists by
    // construction) — zero POST /anchors.
    expect(server.posts.filter((c) => c.url.endsWith("/anchors"))).toHaveLength(0);
    // The link 409-kept honestly (the island's thread holds the anchor).
    await waitFor(() =>
      expect(server.patches.some((c) => c.url.includes("/anchors/"))).toBe(true),
    );
    // The engagement STAYS in the right pane — never a navigation.
    expect(navigateMock).not.toHaveBeenCalled();

    // The ask-to-open; CONFIRM opens exactly one reader window on the
    // derived document with the reformat origin.
    await screen.findByText(/Your reformatted version is ready/);
    fireEvent.click(screen.getByRole("button", { name: "Open it" }));
    const id = readerWindowId("drv-x1");
    const state = useWindows.getState();
    expect(state.order).toEqual([id]);
    expect(state.windows[id].kind).toBe("reader");
    expect(state.windows[id].payload).toEqual({
      documentId: "drv-x1",
      origin: { from: "reformat", id: "reformat:gen-1" },
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("declining the ask opens nothing", async () => {
    const server: Server = { posts: [], patches: [], forkReachable: false };
    route(server);
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    fireEvent.click(await screen.findByRole("button", { name: "Reformat this" }));
    fireEvent.change(screen.getByLabelText("What should the reformat do?"), {
      target: { value: "the 20-minute version" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reformat" }));
    await screen.findByText(/Your reformatted version is ready/);
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(useWindows.getState().order).toHaveLength(0);
    // The honest note — the derived document remains, reachable later.
    await screen.findByText(/in the library whenever you want it/);
  });
});

// ── Proofs 3 + 5: the review surface ───────────────────────────────────────

describe("the derived document's review surface", () => {
  it("renders the honesty header, class markers, the trace jump to the core passage, and the honest null-source line", async () => {
    const server: Server = { posts: [], patches: [], forkReachable: false };
    route(server);
    await renderReader("drv-x1");
    await screen.findByText("The opening of the book.");

    const review = await waitFor(() => {
      const el = document.querySelector("[data-reformat-review]");
      expect(el).toBeTruthy();
      return el!;
    });
    // The honesty header: derived · from the source (human title) · model ·
    // date · provisional.
    expect(review.querySelector("[data-reformat-header]")!.textContent).toContain(
      "A generated reformat of A Servable Book",
    );
    expect(review.querySelector("[data-reformat-header]")!.textContent).toContain("fixture-model");
    expect(review.querySelector("[data-reformat-header]")!.textContent).toContain("provisional");
    // Class markers.
    expect(review.querySelector('[data-reformat-bite="author_verbatim"]')!.textContent).toContain(
      "author's words ✓",
    );
    expect(review.querySelector('[data-reformat-bite="llm_compressed"]')).toBeTruthy();
    // The null-source bite: the honest line, no fabricated span.
    expect(review.querySelector('[data-reformat-bite="llm_expanded"]')!.textContent).toContain(
      "generated connective tissue — no direct source",
    );

    // The trace jump: one click opens the SOURCE at the passage (the anchor
    // payload rides the open call).
    fireEvent.click(document.querySelector('[data-trace-jump="bite-1"]')!);
    const sourceId = readerWindowId("doc-1");
    const state = useWindows.getState();
    expect(state.order).toEqual([sourceId]);
    expect(state.windows[sourceId].payload).toEqual({
      documentId: "doc-1",
      origin: { from: "reformat", id: "gen-1" },
      initialPage: 1,
    });
  });

  it("the ORIGINAL document shows no marker (provenance 404 → no review surface)", async () => {
    const server: Server = { posts: [], patches: [], forkReachable: false };
    route(server);
    await renderReader("doc-1");
    await screen.findByText("The opening of the book.");
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(([u]) => String(u).includes("/provenance")),
      ).toBe(true),
    );
    expect(document.querySelector("[data-reformat-review]")).toBeNull();
  });
});

// ── Proof 4: merge/fork wiring with honest degradation ─────────────────────

describe("merge later / officially fork", () => {
  it("a 404 from the unit-5 contract paths degrades to the named pending state — never a fake success", async () => {
    const server: Server = { posts: [], patches: [], forkReachable: false };
    route(server);
    await renderReader("drv-x1");
    await screen.findByText("The opening of the book.");
    await waitFor(() => expect(document.querySelector("[data-reformat-review]")).toBeTruthy());

    fireEvent.click(document.querySelector("[data-reformat-fork]")!);
    await screen.findByText(/fork\/merge API pending/);
    // No fake success state.
    expect(document.querySelector("[data-reformat-fork]")!.textContent).toBe("Officially fork");
  });

  it("where the fork API IS reachable, the fork carries the generation record's refs", async () => {
    const server: Server = { posts: [], patches: [], forkReachable: true };
    route(server);
    await renderReader("drv-x1");
    await screen.findByText("The opening of the book.");
    await waitFor(() => expect(document.querySelector("[data-reformat-review]")).toBeTruthy());

    fireEvent.click(document.querySelector("[data-reformat-fork]")!);
    await screen.findByText("forked");
    const forkPost = server.posts.find((c) => c.url.endsWith("/forks"))!;
    expect(forkPost.url).toContain("/books/doc-1/forks");
    expect(forkPost.body.derived_document_id).toBe("drv-x1");
    expect(forkPost.body.generation_id).toBe("gen-1");
  });
});
