/**
 * originPrefill.test.tsx — reading-global SPR-02 proof 4: the origin
 * context's ONE consumer. A reader window opened with
 * { from: "research", id } prefills the island's dig-deeper affordance with
 * that investigation as the chase parent (visible in the composer, never
 * silent lineage metadata); a window opened WITHOUT origin — or with a
 * WRITE origin (a deliverable id is never a chase parent) — renders the
 * default affordance (the island's thread parents the chase). The spawn
 * itself crosses the EXISTING startInvestigation path only (no new spawn
 * call — asserted on the network mock surface).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../../api/books";
import type { BookAnchor } from "../../../lib/api";
import { useWorkspace } from "../../../workspace/WorkspaceStore";
import { WindowHostProvider } from "../../../components/windows/windowHostContext";
import { resetReadingStateBus } from "../../../hooks/useReadingState";

const {
  getBookMock,
  getFullTextMock,
  listBooksMock,
  spinResearchMock,
  useInvestigationMock,
  postTypedEventMock,
  searchBlocksMock,
  apiFetchMock,
} = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  spinResearchMock: vi.fn(),
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
    spinResearch: spinResearchMock,
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

function makeDetail(): BookDetail {
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
  };
}

function makeBody(): FullTextResponse {
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

interface Server {
  posts: { url: string; body: Record<string, unknown> }[];
}

function route(server: Server) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    if (method === "POST") server.posts.push({ url, body: parsedBody });

    if (url.endsWith("/investigations") && method === "POST") {
      return jsonResponse(
        { investigation_id: "inv-chase-1", status: "in_progress", start_event_id: "ev-1" },
        201,
      );
    }
    if (url.endsWith("/anchors") && method === "GET") {
      const a = islandAnchor();
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
          { node_id: "q-1", kind: "question", text: "what remains open?", refinement_count: 0, escalated: false },
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

/** The window-mounted reader, with the origin spread into props exactly the
 *  way the window host does (`<Renderer {...win.payload} />`). */
async function renderWindowReaderWithOrigin(origin: { from: string; id: string } | null) {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("../index");
  return render(
    <MemoryRouter initialEntries={["/research"]}>
      <WindowHostProvider value={true}>
        <BookReader documentId="doc-1" origin={origin} />
      </WindowHostProvider>
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
  spinResearchMock.mockReset();
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

async function digFromTheIsland() {
  await screen.findByText("The ope");
  fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
  await screen.findByText("Open research →");
  fireEvent.click(document.querySelector("[data-island-dig-deeper]")!);
  await screen.findByRole("button", { name: "Follow this" });
}

describe("the origin prefill (the origin context's one consumer)", () => {
  it("a research origin prefills the chase parent — visible in the composer, the existing launch path only", async () => {
    const server: Server = { posts: [] };
    route(server);
    await renderWindowReaderWithOrigin({ from: "research", id: "inv-origin-9" });
    await digFromTheIsland();

    // The prefill is VISIBLE — never silent lineage metadata.
    expect(document.querySelector("[data-dig-origin]")!.textContent).toContain(
      "the research you came from",
    );
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));

    await waitFor(() => expect(server.posts).toHaveLength(1));
    // The chase parents to the investigation the operator came from — via
    // the EXISTING startInvestigation path (no new spawn call exists).
    expect(server.posts[0].url).toContain("/investigations");
    expect(server.posts[0].body.parent_investigation_id).toBe("inv-origin-9");
  });

  it("no origin → the default affordance (the island's thread parents the chase, no provenance line)", async () => {
    const server: Server = { posts: [] };
    route(server);
    await renderWindowReaderWithOrigin(null);
    await digFromTheIsland();

    expect(document.querySelector("[data-dig-origin]")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));
    await waitFor(() => expect(server.posts).toHaveLength(1));
    expect(server.posts[0].body.parent_investigation_id).toBe("inv-thread");
  });

  it("a WRITE origin never parents a chase (a deliverable id is not an investigation) — the default holds", async () => {
    const server: Server = { posts: [] };
    route(server);
    await renderWindowReaderWithOrigin({ from: "write", id: "del-1" });
    await digFromTheIsland();

    expect(document.querySelector("[data-dig-origin]")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Follow this" }));
    await waitFor(() => expect(server.posts).toHaveLength(1));
    expect(server.posts[0].body.parent_investigation_id).toBe("inv-thread");
  });
});
