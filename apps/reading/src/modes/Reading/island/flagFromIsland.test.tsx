/**
 * flagFromIsland.test.tsx — the diligence flag affordance on the unit-2
 * island outcome card (autonomous-diligence SPR-01, on the island stack):
 *
 *   - the affordance POSTs exactly ONE flag with the distilled node's id,
 *     the island's thread as source_investigation_id, and enters the queue
 *     as queued;
 *   - THE WITHHELD-SOURCE DOOR: an island on a metadata-only anchor flags a
 *     distilled node with REFS ONLY — the request body carries neither the
 *     node's text nor any withheld passage text (asserted on the body).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../../api/books";
import type { BookAnchor } from "../../../lib/api";
import { useWorkspace } from "../../../workspace/WorkspaceStore";
import { resetReadingStateBus } from "../../../hooks/useReadingState";

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

vi.mock("../../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
  };
});

vi.mock("../../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (e: unknown) => postTypedEventMock(e),
    searchBlocks: (q: string) => searchBlocksMock(q),
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

vi.mock("../../../hooks/useInvestigation", () => ({
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

/** The island anchor — metadata-only (withheld passage): no quote at rest. */
function withheldIslandAnchor(): BookAnchor {
  return {
    anchor_id: "a-island",
    document_id: "doc-1",
    anchor: {
      normalization: "unicode-nfc-v1",
      node_id: "c-1",
      node_text_sha256: "h".repeat(64),
      start_scalar: 0,
      end_scalar: 7,
      quote: "",
      prefix: "",
      suffix: "",
    },
    servable_at_pin: false,
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

const QUESTION_TEXT = "an open question from the thread";

interface FlagServer {
  posts: Record<string, unknown>[];
  flags: unknown[];
}

function route(server: FlagServer) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;

    if (url.endsWith("/diligence/flags") && method === "POST") {
      server.posts.push(parsedBody);
      const row = { flag_id: "dfl-1", status: "queued", ...parsedBody };
      server.flags.push(row);
      return jsonResponse(row, 201);
    }
    if (url.endsWith("/diligence/queue") && method === "GET") {
      return jsonResponse({ flags: server.flags, count: server.flags.length });
    }
    if (url.endsWith("/anchors") && method === "GET") {
      const a = withheldIslandAnchor();
      return jsonResponse({ document_id: "doc-1", anchors: [{ ...a, anchor: { ...a.anchor } }], count: 1 });
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
    if (url.endsWith("/distill")) {
      return jsonResponse({
        investigation_id: "inv-thread",
        insights: [],
        questions: [
          {
            node_id: "q-1",
            kind: "question",
            text: QUESTION_TEXT,
            refinement_count: 0,
            escalated: false,
            source_document_id: "doc-1",
          },
        ],
      });
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

async function renderReader() {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("../index");
  return render(
    <MemoryRouter initialEntries={["/read/doc-1"]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.removeItem("antiek.island.hidden");
  window.localStorage.removeItem("antiek:investigation_tree");
  vi.stubGlobal("fetch", apiFetchMock);
  apiFetchMock.mockReset();
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
  // A completed thread — the island card renders the distilled outcome.
  useInvestigationMock.mockReset().mockReturnValue({
    id: "inv-thread",
    status: "completed",
    question: "the island's question",
    events: [],
    terminalPayload: null,
    costTotal: 0.42,
    completedAt: "2026-09-25T11:00:00Z",
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
  });
  useWorkspace.getState().reset();
  resetReadingStateBus();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the diligence flag on the island outcome card", () => {
  it("flags a distilled question from a WITHHELD-source island — refs only in the request, queued on the server", async () => {
    const server: FlagServer = { posts: [], flags: [] };
    route(server);
    await renderReader();
    // The island mark splits the passage text node (the decorated "The ope"
    // is its own element) — match the mark, per the islands harness.
    await screen.findByText("The ope");

    // Expand the island (a metadata-only anchor: the card shows POSITION,
    // never a quote) and flag the outcome question.
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    await screen.findByText(/an open question from the thread/);
    expect(document.querySelector("[data-island-quote]")).toBeNull();
    expect(document.querySelector("[data-island-position]")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "flag for diligence" }));
    fireEvent.click(screen.getByRole("button", { name: "flag" }));

    await waitFor(() => expect(server.posts).toHaveLength(1));
    const body = server.posts[0];
    expect(body.kind).toBe("open_question");
    expect(body.object_ref).toBe("q-1");
    expect(body.source_investigation_id).toBe("inv-thread");
    expect(body.source_document_id).toBe("doc-1");
    expect(body.note).toBeNull();
    // THE WITHHELD DOOR: neither the node's text nor any passage text rides
    // the flag — refs only.
    const payload = JSON.stringify(body);
    expect(payload).not.toContain(QUESTION_TEXT);
    expect(payload).not.toContain("The opening");
    // The calm confirmation renders in the card.
    await screen.findByText(/flagged — in your diligence queue/);
  });
});
