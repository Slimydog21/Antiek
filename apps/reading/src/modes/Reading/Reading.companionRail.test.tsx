/**
 * Reading.companionRail.test.tsx — the document companion in the rail
 * (companions SPR-02), BOTH reader mounts:
 *
 *   - the companion section renders the generated content with its
 *     provenance markers (data-evidence-id per claim/process) in the
 *     standalone route AND the window-mounted reader — one implementation,
 *     the unit-4 harness;
 *   - a withheld document's section renders METADATA LINES ONLY (the DOM is
 *     grepped for the withheld sentence — absent; the server never sends it);
 *   - the rail stays READ-ONLY (no edit affordance in the companion section
 *     — asserted by DOM query);
 *   - NO raw-HTML injection: the generated narrative renders as structured
 *     content only (the rail path greps clean of dangerouslySetInnerHTML,
 *     asserted at the source level);
 *   - the inspect toggle renders the honest evidence-base dump.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { WindowHostProvider } from "../../components/windows/windowHostContext";
import { resetReadingStateBus } from "../../hooks/useReadingState";

const WITHHELD_SENTENCE = "the withheld sentence that must never render";

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

function companionPayload(servable: boolean) {
  return {
    document_id: "doc-1",
    exists: true,
    title: "A Servable Book",
    servable,
    rebuilt_at: "2026-09-25T12:00:00Z",
    claims: [
      {
        evidence_id: "ev-claim-1",
        kind: "insight",
        node_ref: "node:n-1",
        text: servable ? "the companion's first finding" : null,
      },
      {
        evidence_id: "ev-claim-2",
        kind: "question",
        node_ref: "node:n-2",
        text: servable ? "the companion's open question" : null,
      },
    ],
    anchors: [
      {
        evidence_id: "ev-anchor-1",
        anchor_ref: "anchor:ahl-1",
        status: "active",
        page_index_hint: 0,
      },
    ],
    processes: [
      {
        evidence_id: "ev-proc-1",
        detail: "thread",
        label: "a research thread on a passage",
        status_line: "working…",
      },
    ],
  };
}

function evidenceRows() {
  return {
    rows: [
      { evidence_id: "ev-claim-1", kind: "claim", refs: ["node:n-1", "doc:doc-1"], tombstone: false, rebuilt_at: "2026-09-25T12:00:00Z" },
      { evidence_id: "ev-proc-1", kind: "process", refs: ["investigation:inv-1", "doc:doc-1"], tombstone: false, rebuilt_at: "2026-09-25T12:00:00Z" },
    ],
    count: 2,
  };
}

function route(servable: boolean) {
  apiFetchMock.mockImplementation(async (input: unknown) => {
    const url = String(input);
    if (url.includes("/companion")) {
      return jsonResponse(companionPayload(servable));
    }
    if (url.endsWith("/evidence")) {
      return jsonResponse(evidenceRows());
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
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/read/doc-1"]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function renderWindowReader() {
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  const { default: BookReader } = await import("./index");
  return render(
    <MemoryRouter initialEntries={["/research"]}>
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

describe("the companion rail section in BOTH reader mounts", () => {
  it("standalone route: generated content with provenance markers + the inspect dump", async () => {
    route(true);
    await renderReader();
    await screen.findByText("The opening of the book.");

    const section = await waitFor(() => {
      const el = document.querySelector("[data-companion-section]");
      expect(el).toBeTruthy();
      return el!;
    });
    // Generated content WITH provenance markers (data attrs, never labels).
    expect(section.textContent).toContain("the companion's first finding");
    expect(section.textContent).toContain("a research thread on a passage");
    expect(section.querySelectorAll("[data-evidence-id]").length).toBeGreaterThanOrEqual(3);
    // Read-only: no edit affordance anywhere in the section.
    expect(section.querySelector("textarea, input, [contenteditable]")).toBeNull();

    // The inspect dump: the evidence base's only user surface.
    fireEvent.click(screen.getByRole("button", { name: "inspect evidence base" }));
    const dump = await waitFor(() => {
      const el = document.querySelector("[data-companion-inspect]");
      expect(el).toBeTruthy();
      return el!;
    });
    expect(dump.textContent).toContain("claim");
    expect(dump.textContent).toContain("process");
    expect(dump.textContent).toContain("ev-claim-1");
  });

  it("window-mounted reader: the same section renders (one implementation, both mounts)", async () => {
    route(true);
    await renderWindowReader();
    await screen.findByText("The opening of the book.");
    await waitFor(() =>
      expect(document.querySelector("[data-companion-section]")).toBeTruthy(),
    );
    expect(
      document.querySelector("[data-companion-section]")!.textContent,
    ).toContain("the companion's open question");
  });

  it("a withheld document's section renders metadata lines only — the withheld sentence never enters the DOM", async () => {
    route(false);
    await renderReader();
    await screen.findByText("The opening of the book.");
    const section = await waitFor(() => {
      const el = document.querySelector("[data-companion-section]");
      expect(el).toBeTruthy();
      return el!;
    });
    expect(section.textContent).toContain("withheld");
    expect(section.textContent).toContain("grounded in a withheld source");
    // The grep enforcement at the DOM level: no claim text, and the withheld
    // fixture sentence is nowhere in the document.
    expect(section.textContent).not.toContain("the companion's first finding");
    expect(document.body.textContent).not.toContain(WITHHELD_SENTENCE);
  });

  it("no raw-HTML injection anywhere in the rail path (source-level grep)", () => {
    // The sanctioned-rendering discipline, asserted at the source: the rail
    // and its client render structured content, never generated HTML.
    const fs = require("node:fs") as typeof import("node:fs");
    const path = require("node:path") as typeof import("node:path");
    const rail = fs.readFileSync(
      path.join(__dirname, "ReadingCompanion.tsx"),
      "utf-8",
    );
    const client = fs.readFileSync(
      path.join(__dirname, "../../api/companions.ts"),
      "utf-8",
    );
    expect(rail).not.toContain("dangerouslySetInnerHTML");
    expect(client).not.toContain("dangerouslySetInnerHTML");
    expect(client).not.toContain("innerHTML");
  });
});
