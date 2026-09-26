/**
 * Reading.islands.test.tsx — island SPR-02 proofs (the widget).
 *
 *   - BOTH mounts: a seeded island anchor renders the collapsed status glyph
 *     at the passage; activating expands the pinned overlay card; Esc and
 *     Dismiss collapse; the card is NEVER a workspace window (windowsStore
 *     untouched, asserted).
 *   - Repagination: a page round-trip returns the island widget tied to the
 *     passage (never a stranded overlay).
 *   - Status glyphs: live pulse only via the design system's reduced-motion-
 *     honored pulse; terminal states render their honest glyphs; a gone
 *     thread renders the honest missing-record card.
 *   - Servability: a metadata-only anchor renders NO quote anywhere in the
 *     card (position only); a servable anchor shows the passage quote.
 *   - An island on a drifted anchor renders at the re-resolved passage; on
 *     an orphaned anchor nothing in the body + one honest list row (with the
 *     open-thread link, the parent's "still openable" rule).
 *   - Dismiss collapses for the session; Hide is the per-device preference
 *     (with an honest unhide row); Dig deeper opens the SPR-04 chase
 *     composer inside the card; Open research navigates to /inv/:id.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import type { BookAnchor, DistillationResponse } from "../../lib/api";
import type { InvestigationSummary } from "../../lib/api";
import { useWindows } from "../../workspace/windowsStore";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { resetReadingStateBus } from "../../hooks/useReadingState";
import { WindowHostProvider } from "../../components/windows/windowHostContext";

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

function islandAnchor(over: Partial<BookAnchor> = {}): BookAnchor {
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
    created_at: "2026-09-24T10:00:00Z",
    updated_at: "2026-09-24T10:00:00Z",
    ...over,
  };
}

function summary(over: Partial<InvestigationSummary> = {}): InvestigationSummary {
  return {
    investigation_id: "inv-thread",
    question: "the island's question",
    status: "in_progress",
    started_at: "2026-09-24T10:00:00Z",
    completed_at: null,
    cost_usd_total: 0.42,
    parent_investigation_id: null,
    ...over,
  };
}

function distillation(count: number): DistillationResponse {
  return {
    investigation_id: "inv-thread",
    insights: Array.from({ length: count }, (_, i) => ({
      node_id: `n-${i}`,
      kind: "insight",
      text: `finding ${i}`,
      refinement_count: i === 0 ? 2 : 0,
      escalated: false,
    })),
    questions: [
      { node_id: "q-1", kind: "question", text: "what remains open?", refinement_count: 1, escalated: false },
    ],
  } as DistillationResponse;
}

interface Harness {
  anchors: BookAnchor[];
  investigations: InvestigationSummary[];
}

function route(server: Harness) {
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/anchors") && method === "GET") {
      return jsonResponse({
        document_id: "doc-1",
        anchors: server.anchors.map((r) => ({ ...r, anchor: { ...r.anchor } })),
        count: server.anchors.length,
      });
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
      return jsonResponse(distillation(2));
    }
    if (url.includes("/sessions/")) {
      return jsonResponse({ detail: "not a session" }, 404);
    }
    if (url.includes("/investigations")) {
      return jsonResponse({ count: server.investigations.length, investigations: server.investigations });
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

function projection(status: string) {
  return {
    id: "inv-thread",
    status,
    question: "the island's question",
    events: [],
    terminalPayload: null,
    costTotal: 0.42,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
  };
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.removeItem("antiek.island.hidden");
  vi.stubGlobal("fetch", apiFetchMock);
  apiFetchMock.mockReset();
  getBookMock.mockReset().mockResolvedValue(makeDetail());
  getFullTextMock.mockReset().mockResolvedValue(makeBody());
  listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
  useInvestigationMock.mockReset().mockReturnValue(projection("in_progress"));
  useWorkspace.getState().reset();
  resetReadingStateBus();
  useWindows.getState().reset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.removeItem("antiek.island.hidden");
});

// ── Proof 1: both mounts, expand/collapse, never a workspace window ───────

describe("the island widget in BOTH mounts", () => {
  it("standalone route: the collapsed glyph renders at the passage; expanding opens the pinned card; Esc and Dismiss collapse; never a workspace window", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderReader();
    // The unit-1 mark paints the passage; the island adds the glyph.
    await screen.findByText("The ope");
    const glyphButton = document.querySelector('[data-island-id="a-island"]')!;
    expect(glyphButton.getAttribute("data-island-state")).toBe("collapsed");
    expect(glyphButton.getAttribute("data-island-status")).toBe("live");

    fireEvent.click(glyphButton);
    const card = document.querySelector('[data-island-id="a-island"][data-island-state="expanded"]')!;
    expect(card).toBeTruthy();
    expect(card.getAttribute("role")).toBe("dialog");
    expect(card.textContent).toContain("the island's question");
    expect(card.textContent).toContain("working…");
    expect(card.textContent).toContain("$0.42");
    // The card is pinned beside the passage's mark, inside the island layer —
    // and it is NEVER a workspace window.
    expect(document.querySelector("[data-island-layer]")).toBeTruthy();
    expect(useWindows.getState().order).toHaveLength(0);

    // Esc collapses; re-expand; Dismiss (×) collapses.
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(document.querySelector('[data-island-id="a-island"]')!.getAttribute("data-island-state")).toBe("collapsed"),
    );
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    await screen.findByText("Open research →");
    fireEvent.click(screen.getByLabelText("Dismiss the island"));
    await waitFor(() =>
      expect(document.querySelector('[data-island-id="a-island"]')!.getAttribute("data-island-state")).toBe("collapsed"),
    );
    expect(useWindows.getState().order).toHaveLength(0);
  });

  it("window-mounted reader: the island renders the same way (one implementation, both mounts)", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderWindowReader("doc-1");
    await screen.findByText("The ope");
    const glyphButton = document.querySelector('[data-island-id="a-island"]')!;
    expect(glyphButton.getAttribute("data-island-state")).toBe("collapsed");
    fireEvent.click(glyphButton);
    await screen.findByText("Open research →");
    expect(useWindows.getState().order).toHaveLength(0);
  });

  it("a page round-trip returns the island widget tied to the passage (never stranded)", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(screen.getByText("Next →"));
    await screen.findByText("The second page.");
    expect(document.querySelector('[data-island-id="a-island"]')).toBeNull();
    fireEvent.click(screen.getByText("← Previous"));
    await screen.findByText("The ope");
    expect(document.querySelector('[data-island-id="a-island"]')).toBeTruthy();
  });
});

// ── Proof 3: the status glyphs ────────────────────────────────────────────

describe("the status glyphs", () => {
  it("live pulses via the design system's reduced-motion-honored pulse only", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderReader();
    await screen.findByText("The ope");
    const glyph = document.querySelector("[data-island-glyph]")!;
    expect(glyph.className).toContain("animate-pulse");
    expect(glyph.className).toContain("motion-reduce:animate-none");
    expect(glyph.className).toContain("bg-sun");
  });

  it("terminal states render their honest glyphs; gone renders the missing-record card", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    useInvestigationMock.mockReturnValue(projection("completed"));
    await renderReader();
    await screen.findByText("The ope");
    const btn = document.querySelector('[data-island-id="a-island"]')!;
    expect(btn.getAttribute("data-island-status")).toBe("complete");
    const glyph = btn.querySelector("[data-island-glyph]")!;
    expect(glyph.className).toContain("bg-sun");
    expect(glyph.className).not.toContain("animate-pulse");

    fireEvent.click(btn);
    await screen.findByText("finding 0");
    expect(document.querySelector('[data-island-insights]')!.textContent).toContain("refined ×2");
    expect(document.querySelector('[data-island-questions]')!.textContent).toContain("what remains open?");
    expect(document.querySelector('[data-island-questions]')!.textContent).toContain("refined ×1");
  });

  it("a gone thread renders the honest missing-record card", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    useInvestigationMock.mockReturnValue(projection("not_found"));
    await renderReader();
    await screen.findByText("The ope");
    const btn = document.querySelector('[data-island-id="a-island"]')!;
    expect(btn.getAttribute("data-island-status")).toBe("gone");
    fireEvent.click(btn);
    await screen.findByText(/record is missing/);
    expect(document.querySelector("[data-island-gone]")).toBeTruthy();
  });
});

// ── Proof 4: the servability boundary ─────────────────────────────────────

describe("the servability boundary", () => {
  it("a metadata-only anchor renders NO quote anywhere in the card — position only", async () => {
    route({
      anchors: [
        islandAnchor({
          anchor_id: "a-private",
          servable_at_pin: false,
          page_index_hint: 2,
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
        }),
      ],
      investigations: [summary()],
    });
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(document.querySelector('[data-island-id="a-private"]')!);
    const card = await screen.findByRole("dialog");
    expect(document.querySelector("[data-island-quote]")).toBeNull();
    expect(card.textContent).not.toContain("“The ope”");
    expect(document.querySelector("[data-island-position]")!.textContent).toMatch(/page 3/i);
  });

  it("a servable anchor shows the passage quote in the card", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    const quote = document.querySelector("[data-island-quote]")!;
    expect(quote).toBeTruthy();
    expect(quote.textContent).toContain("The ope");
  });
});

// ── Proof 5: drifted and orphaned inheritance ─────────────────────────────

describe("drifted and orphaned inheritance (the parent's rule)", () => {
  it("an island on a drifted anchor renders at the re-resolved passage", async () => {
    route({
      anchors: [islandAnchor({ status: "drifted" })],
      investigations: [summary()],
    });
    await renderReader();
    const mark = await screen.findByText("The ope");
    expect(mark.getAttribute("data-anchor-treatment")).toBe("drifted");
    const glyphButton = document.querySelector('[data-island-id="a-island"]')!;
    expect(glyphButton).toBeTruthy();
    fireEvent.click(glyphButton);
    await screen.findByText("Open research →");
  });

  it("an island on an orphaned anchor renders nothing in the body and one honest list row (still openable)", async () => {
    route({
      anchors: [islandAnchor({ anchor_id: "a-gone", status: "orphaned", page_index_hint: 1 })],
      investigations: [summary()],
    });
    await renderReader();
    await screen.findByText("The opening of the book.");
    expect(document.querySelector('[data-island-id="a-gone"]')).toBeNull();
    const row = document.querySelector('[data-orphaned-anchor="a-gone"]')!;
    expect(row.textContent).toContain("Page 2");
    expect(row.textContent).toContain("text no longer found");
    const open = row.querySelector("[data-orphaned-island-open]")!;
    expect(open.getAttribute("href")).toBe("/inv/inv-thread");
  });
});

// ── Actions: open / dig-deeper stub / dismiss-session / hide-per-device ───

describe("the island actions", () => {
  it("Open research links to /inv/:id; Dig deeper opens the SPR-04 chase composer inside the card", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    const open = await screen.findByText("Open research →");
    expect(open.closest("a")!.getAttribute("href")).toBe("/inv/inv-thread");
    const dig = document.querySelector("[data-island-dig-deeper]")! as HTMLButtonElement;
    expect(dig.disabled).toBe(false);
    fireEvent.click(dig);
    // The composer opens INSIDE the card: the passage quote prefilled, the
    // question textarea, the chase's one-line cost semantics.
    const composer = document.querySelector("[data-dig-deeper]")!;
    expect(composer).toBeTruthy();
    expect(composer.querySelector("[data-dig-quote]")!.textContent).toContain("The ope");
    expect(screen.getByRole("button", { name: "Follow this" })).toBeTruthy();
    expect(composer.querySelector("[data-dig-chase-cost]")!.textContent).toContain(
      "new child investigation",
    );
    // Cancel returns to the action row.
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.querySelector("[data-dig-deeper]")).toBeNull();
  });

  it("Hide removes the island for this device with an honest unhide row (nothing is deleted)", async () => {
    route({ anchors: [islandAnchor()], investigations: [summary()] });
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    fireEvent.click(await screen.findByText("Hide"));
    await waitFor(() =>
      expect(document.querySelector('[data-island-id="a-island"]')).toBeNull(),
    );
    // The anchor and thread are untouched — only the device preference hides.
    const row = document.querySelector('[data-hidden-island="a-island"]')!;
    expect(row).toBeTruthy();
    expect(row.textContent).toContain("hidden island");
    fireEvent.click(row.querySelector("button")!);
    await screen.findByText("The ope");
    expect(document.querySelector('[data-island-id="a-island"]')).toBeTruthy();
    expect(window.localStorage.getItem("antiek.island.hidden")).not.toContain("a-island");
  });

  it("a thread family renders root + chases with per-node status", async () => {
    route({
      anchors: [islandAnchor()],
      investigations: [
        summary({ investigation_id: "inv-thread", question: "root q" }),
        summary({ investigation_id: "chase-1", parent_investigation_id: "inv-thread", status: "completed", question: "chase q" }),
      ],
    });
    await renderReader();
    await screen.findByText("The ope");
    fireEvent.click(document.querySelector('[data-island-id="a-island"]')!);
    const family = document.querySelector("[data-island-family]")!;
    expect(family.textContent).toContain("root q");
    expect(family.textContent).toContain("chase q");
    expect(family.textContent).toContain("done");
  });
});
