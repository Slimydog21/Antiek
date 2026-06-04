import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor, renderHook, act, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { paginate, windowForTocPage } from "./paginate";
import { usePosition } from "./usePosition";
import { useReaderImpressions } from "./useReaderImpressions";

const {
  getBookMock,
  getFullTextMock,
  listBooksMock,
  spinResearchMock,
  recordAdImpressionsMock,
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
  recordAdImpressionsMock: vi.fn().mockResolvedValue(undefined),
  navigateMock: vi.fn(),
  useInvestigationMock: vi.fn(),
  postTypedEventMock: vi.fn((_e: unknown) =>
    Promise.resolve({ event_id: "ev-1", action_type: "marginalia.noted" }),
  ),
  searchBlocksMock: vi.fn((_q: string) => Promise.resolve({ count: 0, hits: [] })),
  startInvestigationMock: vi.fn((_r: unknown) =>
    Promise.resolve({ investigation_id: "child-1", status: "in_progress", start_event_id: "ev-s" }),
  ),
  apiFetchMock: vi.fn((_i: unknown, _init?: unknown) =>
    Promise.resolve(new Response(JSON.stringify({ text: "reply" }), { status: 200 })),
  ),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
    spinResearch: spinResearchMock,
    recordAdImpressions: recordAdImpressionsMock,
  };
});

// The in-book FloatMenu host (M2) reaches lib/api through floatMenuActions +
// sourceRead. Mock at the api boundary only (real components otherwise).
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

// ReadingCompanion (M2) + ChaseThread's launched stream (M3) read the book's
// reading thread through this hook. A calm, not-running thread keeps the
// companion in its honest empty state for the gesture tests.
vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

afterEach(() => cleanup());

// ── jsdom selection helper (mirrors FloatMenu.test.tsx) ──────────────
// Build a REAL Range over the text node inside the scope element so the
// shared useFloatMenuSelection hook's `scope.contains(range.…)` narrowing
// passes, give the range a rect, and fire `selectionchange`.
function selectTextIn(
  scope: HTMLElement,
  text: string,
  rect = { top: 200, left: 100, width: 80, height: 18 },
): void {
  const node = scope.firstChild as Node | null;
  const range = document.createRange();
  if (node) {
    range.selectNodeContents(node);
  } else {
    range.selectNodeContents(scope);
  }
  range.getBoundingClientRect = () =>
    ({
      ...rect,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
      toJSON() {
        return rect;
      },
    }) as DOMRect;
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

// ── paginate (the locator scheme) ───────────────────────────────────

describe("paginate", () => {
  it("splits served markdown on `## Page N`, dropping front matter", () => {
    const md = "# Title\n_by Author_\n## Page 1\n\nfirst page body\n\n## Page 2\n\nsecond page body";
    const pages = paginate(md);
    expect(pages.map((p) => p.pageNumber)).toEqual([1, 2]);
    expect(pages[0].pageIndex).toBe(0);
    expect(pages[0].text).toContain("first page body");
    expect(pages[0].text).not.toContain("# Title"); // front matter dropped
    expect(pages[1].text).toContain("second page body");
  });

  it("returns a single window for unpaginated text (a snippet)", () => {
    const pages = paginate("just a short snippet, no markers");
    expect(pages).toHaveLength(1);
    expect(pages[0].pageIndex).toBe(0);
  });

  it("returns nothing for empty body", () => {
    expect(paginate("")).toEqual([]);
  });

  it("windowForTocPage clamps into range", () => {
    const pages = paginate("## Page 1\n\na\n\n## Page 2\n\nb");
    expect(windowForTocPage(pages, 5)).toBe(1); // clamps to last
    expect(windowForTocPage(pages, null)).toBeNull();
    expect(windowForTocPage([], 0)).toBeNull();
  });
});

// ── usePosition (return-to-reading) ─────────────────────────────────

describe("usePosition", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("persists and restores the page index per document", () => {
    const { result, unmount } = renderHook(() => usePosition("doc-a", 10));
    act(() => result.current.setPageIndex(4));
    expect(result.current.pageIndex).toBe(4);
    unmount();
    // A fresh mount of the same document restores position 4.
    const { result: r2 } = renderHook(() => usePosition("doc-a", 10));
    expect(r2.current.pageIndex).toBe(4);
  });

  it("clamps a saved position past the end of a shorter book", () => {
    window.sessionStorage.setItem("antiek.read.pos.doc-b", "99");
    const { result } = renderHook(() => usePosition("doc-b", 3));
    expect(result.current.pageIndex).toBe(2); // clamped to last page
  });
});

// ── useReaderImpressions (SPR-05 flush loop) ────────────────────────

describe("useReaderImpressions", () => {
  beforeEach(() => recordAdImpressionsMock.mockClear());

  it("flushes the previous page's slots when the page changes", () => {
    const houseFill = { kind: "house" as const, house: null };
    const { result } = renderHook(() => useReaderImpressions("doc-1", "sess-1"));
    act(() => {
      result.current.observePage(0, [
        { slotId: "slot:doc-1:p0:top", fill: houseFill },
        { slotId: "slot:doc-1:p0:bottom", fill: houseFill },
      ]);
    });
    // No flush yet — page 0 is still showing.
    expect(recordAdImpressionsMock).not.toHaveBeenCalled();
    // Move to page 1 → page 0's slots flush.
    act(() => {
      result.current.observePage(1, [{ slotId: "slot:doc-1:p1:top", fill: houseFill }]);
    });
    expect(recordAdImpressionsMock).toHaveBeenCalledTimes(1);
    const [doc, session, items] = recordAdImpressionsMock.mock.calls[0];
    expect(doc).toBe("doc-1");
    expect(session).toBe("sess-1");
    expect(items.map((i: { slot_id: string }) => i.slot_id)).toEqual([
      "slot:doc-1:p0:top",
      "slot:doc-1:p0:bottom",
    ]);
    expect(items[0].page_index).toBe(0);
    expect(items[0].fill_kind).toBe("house");
  });
});

// ── BookReader (gate-aware rendering) ───────────────────────────────

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
  // Default to a NON-arXiv document (tier null): ad-eligibility equals servable
  // (today's behaviour), no canonical/license. arXiv cases override `tier`
  // (and ad_eligible/canonical_url/license) explicitly per the SPR-05 contract.
  const servable = over.servable ?? true;
  return {
    document_id: "doc-1",
    servable: true,
    servability: "public_domain",
    full_text: "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.",
    snippet: null,
    title: "A Servable Book",
    author: "Auth",
    reason: "servable",
    tier: null,
    ad_eligible: servable,
    canonical_url: null,
    license: null,
    ...over,
  };
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

describe("BookReader", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    getBookMock.mockReset();
    getFullTextMock.mockReset();
    listBooksMock.mockReset();
    navigateMock.mockReset();
    // Default: a calm, empty reading thread (the no-key / nothing-yet case).
    useInvestigationMock.mockReset();
    useInvestigationMock.mockReturnValue({
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

  it("renders a servable book's full text with a working pager", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody());
    await renderReader();
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    expect(screen.getByText(/Page 1 of 2/)).toBeTruthy(); // pager text (matcher spans nodes)
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    await waitFor(() => expect(screen.getByText("The second page.")).toBeTruthy());
  });

  it("shows the preview banner and snippet for a gated book", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({ servable: false, full_text: null, snippet: "Only a snippet is permitted.", reason: "gated_metadata_only" }),
    );
    await renderReader();
    await waitFor(() =>
      expect(screen.getByText(/licensed for full reading/)).toBeTruthy(),
    );
    expect(screen.getByText("Only a snippet is permitted.")).toBeTruthy();
  });

  it("shows a removed notice for a taken-down book", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "taken_down", servable_full_text: false, taken_down: true }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({ servable: false, full_text: null, snippet: null, servability: "taken_down", reason: "taken_down" }),
    );
    await renderReader();
    await waitFor(() => expect(screen.getByText(/has been removed/)).toBeTruthy());
  });

  it("renders a not-found note for an unknown book", async () => {
    getBookMock.mockRejectedValue(new Error("book_not_found"));
    getFullTextMock.mockRejectedValue(new Error("book_not_found"));
    await renderReader();
    await waitFor(() => expect(screen.getByText(/in the library/)).toBeTruthy());
  });

  it("spins a research from the current page and hands off to it", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody());
    spinResearchMock.mockResolvedValue({
      investigation_id: "inv-child-xyz",
      document_id: "doc-1",
      page_index: 0,
      gated: false,
      servability: "public_domain",
      seed_preview: "From the book…",
    });
    navigateMock.mockReset();
    await renderReader();
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Research this page/ }));
    await waitFor(() => expect(spinResearchMock).toHaveBeenCalled());
    // Seeds from the current page index (0) and hands off to the research.
    expect(spinResearchMock).toHaveBeenCalledWith("doc-1", 0, expect.stringContaining("opening"));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-child-xyz"));
  });

  // ── Read SPR-06 M2/M3: companion rail + inline rabbit-hole ──────────

  it("mounts the reading companion beside an open book (M2 glass-box)", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody());
    await renderReader();
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    // The companion is docked beside the reading column.
    expect(screen.getByRole("complementary", { name: /Reading companion/ })).toBeTruthy();
    // Empty, not-running thread ⇒ honest empty state, no fabricated notes.
    expect(screen.getByText(/No notes yet/)).toBeTruthy();
  });

  // ── SPR-07 M2/M3: the SHARED SPR-04 float-menu, in-book ─────────────

  it("highlighting a passage opens the SAME SPR-04 float-menu in-book (reused, not re-implemented)", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody());
    await renderReader();
    const para = await screen.findByText("The opening of the book.");

    // No menu until there is a real highlight.
    expect(screen.queryByRole("menu", { name: /Highlight actions/ })).toBeNull();

    // Highlight a passage inside the page <article>.
    selectTextIn(para, "The opening of the book.");

    // The identical four-action float-menu opens (the SAME component Research
    // uses — verified by import at the top of index.tsx).
    const menu = await screen.findByRole("menu", { name: /Highlight actions/ });
    expect(within(menu).getByRole("menuitem", { name: "Note" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Dialogue" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Search" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Deep-research" })).toBeTruthy();
  });

  it("the in-book NOTE persists via postTypedEvent to the reading thread with a user-sourced label + provenance (M2/M3)", async () => {
    postTypedEventMock.mockClear();
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody());
    await renderReader();
    const para = await screen.findByText("The opening of the book.");
    selectTextIn(para, "The opening of the book.");

    const menu = await screen.findByRole("menu", { name: /Highlight actions/ });
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Note" }));
    const textarea = await screen.findByPlaceholderText(/Type a note/);
    fireEvent.change(textarea, { target: { value: "a thought while reading" } });
    fireEvent.click(screen.getByRole("button", { name: /Save note/ }));

    await waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    const env = postTypedEventMock.mock.calls[0][0] as {
      investigation_id: string;
      document_id?: string;
      payload: { action_type: string; source_kind: string; note_text: string };
    };
    // Lands on THIS book's reading thread (read-<documentId>) → the companion.
    expect(env.investigation_id).toBe("read-doc-1");
    expect(env.document_id).toBe("doc-1"); // provenance: document on the envelope
    expect(env.payload.action_type).toBe("marginalia.noted");
    expect(env.payload.source_kind).toBe("user"); // §9 user-sourced label
    expect(env.payload.note_text).toBe("a thought while reading");
  });

  it("Deep-research in-book routes to the SAME ChaseThread, seeded with the passage, with a way home (generalized rabbit-hole, M2/M3)", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody());
    await renderReader();
    const para = await screen.findByText("The opening of the book.");
    selectTextIn(para, "The opening of the book.");

    const menu = await screen.findByRole("menu", { name: /Highlight actions/ });
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Deep-research" }));

    // The inline chase mounts beside the reading column (the SAME ChaseThread
    // the old "Go deeper" affordance used — now one of four float-menu actions).
    const chasePanel = await screen.findByRole("complementary", { name: /Following this passage/ });
    const lifted = within(chasePanel).getAllByText(/The opening of the book\./);
    expect(lifted.length).toBeGreaterThanOrEqual(1);
    const back = screen.getByRole("button", { name: /back to the book/ });
    fireEvent.click(back);
    // Reversible: back to the companion, position held by usePosition.
    expect(screen.getByRole("complementary", { name: /Reading companion/ })).toBeTruthy();
  });

  it("a taken-down (restricted) book renders no body — nothing to read, highlight, or chase (servable-corpus honesty, §9.0)", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "taken_down", servable_full_text: false, taken_down: true }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({ servable: false, full_text: null, snippet: null, servability: "taken_down", reason: "taken_down" }),
    );
    await renderReader();
    await waitFor(() => expect(screen.getByText(/has been removed/)).toBeTruthy());
    // The body is never served, so there is no page to highlight and no
    // float-menu — the gate withholds at the source, the reader reflects it.
    expect(screen.getByText(/no readable pages/)).toBeTruthy();
    expect(screen.queryByRole("menu", { name: /Highlight actions/ })).toBeNull();
  });

  // ── Read SPR-05: tiered reader surface (T1/T2/T3 + ad-gating) ───────
  //
  // The reader reads tier / ad-eligibility / canonical link off the GATE
  // response (never a local flag). The AdBorder rails carry data-slot-id +
  // aria-label="Recommended reading" (the house-fill state); their presence/
  // absence in the DOM is the ad-gating assertion.

  function adRails(container: HTMLElement): NodeListOf<Element> {
    return container.querySelectorAll("[data-slot-id]");
  }

  it("T1 arXiv: hosts the extracted body, shows ad rails, Attribution + a canonical via-arXiv link", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "public_domain", servable_full_text: true }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        tier: "T1",
        ad_eligible: true,
        canonical_url: "https://arxiv.org/abs/2401.00001",
        license: "https://creativecommons.org/publicdomain/zero/1.0/",
      }),
    );
    const { container } = await renderReader();
    // The hosted extracted text renders through the SAME markdown reader.
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    // Ad rails present (T1 is ad-eligible).
    expect(adRails(container).length).toBeGreaterThan(0);
    // Attribution chrome + a canonical link that points at arxiv.org.
    const attribution = container.querySelector("[aria-label='Attribution']") as HTMLElement;
    expect(attribution).toBeTruthy();
    const viaArxiv = within(attribution).getByText(/via arXiv/);
    expect(viaArxiv.getAttribute("href")).toBe("https://arxiv.org/abs/2401.00001");
    // No link-back frame on T1 — it hosts the body.
    expect(container.querySelector("[data-arxiv-frame]")).toBeNull();
  });

  it("T2 arXiv (gated): renders the arXiv link-back, NO ad rails, NO hosted body, Attribution", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: null,
        tier: "T2",
        ad_eligible: false,
        canonical_url: "https://arxiv.org/abs/2402.00002",
        license: "https://creativecommons.org/licenses/by-nc/4.0/",
        reason: "gated_metadata_only",
        servability: "gated_metadata_only",
      }),
    );
    const { container } = await renderReader();
    // The link-back frame is the surface; its canonical target is arxiv.org
    // (DOM-inspectable on data-canonical-url — the bare full-URL anchor was
    // trimmed; the "Read on arXiv" CTA + Attribution's link are the two links).
    const frame = await waitFor(() => {
      const f = container.querySelector("[data-arxiv-frame]") as HTMLElement | null;
      expect(f).toBeTruthy();
      return f as HTMLElement;
    });
    expect(frame.getAttribute("data-canonical-url")).toBe("https://arxiv.org/abs/2402.00002");
    expect(within(frame).getByText(/Read on arXiv/)).toBeTruthy();
    // NO ad rails — body-serving + ads are {T1}-only.
    expect(adRails(container).length).toBe(0);
    // No hosted body reached the DOM (the gate served none, and we host none).
    expect(screen.queryByText("The opening of the book.")).toBeNull();
    // Attribution still renders (all tiers).
    expect(container.querySelector("[aria-label='Attribution']")).toBeTruthy();
    // §9.0 / rights: NO Antiek-served body — the only arXiv pointer is the
    // canonical arxiv.org URL (bytes come from arXiv, never proxied by Antiek).
    expect(container.querySelector("[data-akb-asset-id]")).toBeNull();
  });

  it("T3 arXiv (unknown/default): same link-back path as T2, NO ad rails, NO hosted body", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: null,
        tier: "T3",
        ad_eligible: false,
        canonical_url: "https://arxiv.org/abs/2403.00003",
        license: null,
        reason: "restricted_pending_opt_in",
        servability: "gated_metadata_only",
      }),
    );
    const { container } = await renderReader();
    const frame = await waitFor(() => {
      const f = container.querySelector("[data-arxiv-frame]") as HTMLElement | null;
      expect(f).toBeTruthy();
      return f as HTMLElement;
    });
    expect(frame.getAttribute("data-canonical-url")).toBe("https://arxiv.org/abs/2403.00003");
    expect(within(frame).getByText(/Read on arXiv/)).toBeTruthy();
    expect(adRails(container).length).toBe(0);
    expect(screen.queryByText("The opening of the book.")).toBeNull();
    expect(container.querySelector("[aria-label='Attribution']")).toBeTruthy();
  });

  it("non-arXiv servable book: keeps its ad rails (regression — ad-gating must not turn them off)", async () => {
    // tier null + ad_eligible true (the backend sets ad_eligible == servable for
    // a non-arXiv work). This is exactly today's path and MUST keep the rails.
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody()); // tier:null, ad_eligible:true
    const { container } = await renderReader();
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    expect(adRails(container).length).toBeGreaterThan(0);
    // A non-arXiv doc has no canonical arXiv source, so Attribution renders
    // nothing extra (no via-arXiv link).
    expect(screen.queryByText(/via arXiv/)).toBeNull();
    // Never a link-back frame for a non-arXiv work.
    expect(container.querySelector("[data-arxiv-frame]")).toBeNull();
  });

  it("non-arXiv gated book: existing preview notice preserved + NO ad rails (ad_eligible false)", async () => {
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: "Only a snippet is permitted.",
        ad_eligible: false, // tier stays null (non-arXiv)
        reason: "gated_metadata_only",
        servability: "gated_metadata_only",
      }),
    );
    const { container } = await renderReader();
    // The existing gated notice is unchanged (no arXiv branch hijacked it).
    await waitFor(() => expect(screen.getByText(/licensed for full reading/)).toBeTruthy());
    expect(screen.getByText("Only a snippet is permitted.")).toBeTruthy();
    // A non-ad-eligible gated work shows no ad rails.
    expect(adRails(container).length).toBe(0);
    // And it is NOT routed to the arXiv link-back frame (tier null).
    expect(container.querySelector("[data-arxiv-frame]")).toBeNull();
  });

  // ── Read SPR-05 (round-2): the ad-eligibility gate is LOAD-BEARING ───
  //
  // The observePage slot list is gated on `body.ad_eligible`. A non-ad-eligible
  // doc that HAS pages must register ZERO impression slots — registering top+
  // bottom regardless would flush FALSE impressions into the SPR-06 accrual/
  // money path. These two tests are the mutation guard: removing the
  // `body?.ad_eligible &&` conditional (registering slots regardless) MUST turn
  // the first one red.

  it("LOAD-BEARING: a non-ad-eligible doc WITH pages registers ZERO impression slots (no false impressions)", async () => {
    recordAdImpressionsMock.mockClear();
    // A non-arXiv GATED book with a snippet: servable=false ⇒ ad_eligible=false,
    // full_text=null, snippet present ⇒ paginates to exactly one page. So the
    // observePage effect DOES run (pages.length === 1) — the discriminating
    // input: a body that has pages but is NOT ad-eligible.
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: "A gate-served snippet, one page of it.",
        ad_eligible: false,
        servability: "gated_metadata_only",
        reason: "gated_metadata_only",
      }),
    );
    const { container, unmount } = await renderReader();
    // The snippet body paginated (pages exist), so observePage ran with the
    // registered slot list — which, for a non-ad-eligible doc, MUST be empty.
    await waitFor(() =>
      expect(screen.getByText("A gate-served snippet, one page of it.")).toBeTruthy(),
    );
    // No ad rails on screen either (the render gate agrees with the slot gate).
    expect(adRails(container).length).toBe(0);
    // Unmount flushes the current page. With an EMPTY slot list the hook never
    // calls recordAdImpressions (no slot ⇒ no impression). If the ad-eligibility
    // conditional were removed, top+bottom slots would be registered and this
    // unmount flush WOULD fire recordAdImpressions — so this assertion is the
    // mutation guard.
    unmount();
    const adImpressionCalls = recordAdImpressionsMock.mock.calls.filter(
      ([, , items]) =>
        Array.isArray(items) &&
        items.some((i: { slot_id: string }) => /:top$|:bottom$/.test(i.slot_id)),
    );
    expect(adImpressionCalls).toHaveLength(0);
    expect(recordAdImpressionsMock).not.toHaveBeenCalled();
  });

  it("LOAD-BEARING: an ad-eligible doc DOES flush top+bottom ad impressions on a page change", async () => {
    recordAdImpressionsMock.mockClear();
    // A non-arXiv servable book: ad_eligible=true, multi-page body, so a Next
    // click drives a real page change → the previous page's top+bottom slots
    // flush. This is the positive half: the gate lets eligible rails through.
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody()); // tier null, ad_eligible true, 2 pages
    await renderReader();
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    await waitFor(() => expect(recordAdImpressionsMock).toHaveBeenCalled());
    // The flushed impressions are the previous page's top+bottom ad slots.
    const flushed = recordAdImpressionsMock.mock.calls.flatMap(([, , items]) =>
      (items as { slot_id: string }[]).map((i) => i.slot_id),
    );
    expect(flushed.some((s) => /:top$/.test(s))).toBe(true);
    expect(flushed.some((s) => /:bottom$/.test(s))).toBe(true);
  });

  it("a content-gated ad-eligible doc with NO stored body (full_text null, no pages) shows NO ad rails", async () => {
    // An arXiv T1 whose license makes it ad-eligible, but whose body isn't
    // stored yet: ad_eligible=true, full_text=null, snippet=null ⇒ pages.length
    // 0. The rails must NOT mount around nothing. (Render is gated on
    // `adEligible && pages.length > 0`.)
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "public_domain", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        tier: "T1",
        ad_eligible: true,
        full_text: null,
        snippet: null,
        canonical_url: "https://arxiv.org/abs/2401.99999",
        license: "https://creativecommons.org/publicdomain/zero/1.0/",
        servable: false,
        reason: "body_not_stored",
      }),
    );
    const { container } = await renderReader();
    // Attribution still renders (T1 with canonical), but there are NO ad rails
    // because there is no body to wrap.
    await waitFor(() =>
      expect(container.querySelector("[aria-label='Attribution']")).toBeTruthy(),
    );
    expect(adRails(container).length).toBe(0);
    // Not the link-back frame either — T1 is the hosted-body tier (just empty).
    expect(container.querySelector("[data-arxiv-frame]")).toBeNull();
  });

  it("a degenerate arXiv T2/T3 with canonical_url null degrades honestly — no body, no ad rails, an honest notice", async () => {
    // Defence-in-depth: unreachable from the OAI persist path (arxiv_id is co-
    // stamped with license_uri), but if a T2/T3 doc lost its canonical_url it
    // must NOT fall through to the empty hosted-body view. It renders the
    // link-unavailable notice and nothing else.
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: null,
        tier: "T3",
        ad_eligible: false,
        canonical_url: null,
        license: null,
        servability: "gated_metadata_only",
        reason: "restricted_pending_opt_in",
      }),
    );
    const { container } = await renderReader();
    await waitFor(() =>
      expect(container.querySelector("[data-arxiv-link-unavailable]")).toBeTruthy(),
    );
    expect(screen.getByText(/arXiv link isn’t available/)).toBeTruthy();
    // No empty body, no link-back frame, no ad rails.
    expect(container.querySelector("[data-arxiv-frame]")).toBeNull();
    expect(adRails(container).length).toBe(0);
    expect(screen.queryByText("The opening of the book.")).toBeNull();
  });

  it("a gated book: a highlight on the bounded snippet refuses outbound Search — the withheld body never leaves the client (§9.0 no-leak)", async () => {
    // The §9.0 safety rests on TWO layers: (1) the reader renders only the gate-
    // served body (a gated book serves a bounded snippet, full_text withheld);
    // (2) the FloatMenu's outboundText chokepoint refuses Search/Deep-research
    // over a non-servable selection (servable===false from resolveProvenance,
    // which reads book.servable_full_text). This pins BOTH: only the snippet is
    // on screen, AND an outbound Search over it is refused (searchBlocks never
    // called — the body never leaves the client).
    searchBlocksMock.mockClear();
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
    await renderReader();
    // Only the gate-served snippet is on screen (full_text was withheld).
    const para = await screen.findByText(/A short gate-served preview\./);
    selectTextIn(para, "A short gate-served preview.");

    const menu = await screen.findByRole("menu", { name: /Highlight actions/ });
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Search" }));

    // The chokepoint refuses: the withheld reason shows, and searchBlocks was
    // NEVER called — the snippet body never left the client.
    await waitFor(() =>
      expect(screen.getByText(/includes a restricted source/)).toBeTruthy(),
    );
    expect(searchBlocksMock).not.toHaveBeenCalled();
  });

  // ── Reader SPR-03 M4: the ONE <Reader> for structured-blocks docs ───
  //
  // A servable book whose serve response carries `structured_blocks` renders
  // through the rich typed-block <Reader>; a NULL/absent column falls back to
  // the legacy ReadingColumn flattener; a gated book NEVER rich-renders and is
  // NEVER attribution-tagged (§9.0); the ad-impression slot count equals the
  // rendered page count (no false impressions).

  // A serialized SPR-01 Document with two heading-led pages' worth of blocks.
  // 14 blocks @ DEFAULT_BLOCKS_PER_PAGE=12 ⇒ exactly 2 block windows, so the
  // rich path is multi-page (exercises the pager + ad-slot count alignment).
  function structuredBlocksJson(): string {
    const blocks: unknown[] = [
      { type: "heading", level: 1, spans: [{ type: "text", text: "Chapter One" }] },
      { type: "paragraph", spans: [{ type: "text", text: "A richly typeset opening paragraph." }] },
    ];
    // Pad to 14 total blocks so paginateBlocks yields 2 windows (12 + 2).
    for (let i = 0; i < 12; i++) {
      blocks.push({ type: "paragraph", spans: [{ type: "text", text: `Body paragraph ${i}.` }] });
    }
    // Put a heading on the second window so the derived ToC has 2 entries.
    blocks.push({ type: "heading", level: 2, spans: [{ type: "text", text: "Chapter Two" }] });
    return JSON.stringify({ id: "doc-1", title: "A Servable Book", schema_version: 1, blocks });
  }

  function richArticle(container: HTMLElement): HTMLElement | null {
    return container.querySelector("article[data-reader-root]") as HTMLElement | null;
  }

  it("renders the rich <Reader> for a structured-blocks servable doc (not the legacy flattener)", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: structuredBlocksJson() }));
    const { container } = await renderReader();
    // The rich typed-block heading renders (the flattener collapsed all headings
    // to one <h2>; the Reader renders a real <h1>). The presence of the
    // data-reader-root article is the discriminator.
    await waitFor(() => expect(richArticle(container)).toBeTruthy());
    expect(screen.getByText("A richly typeset opening paragraph.")).toBeTruthy();
    // The rich heading renders as an actual heading element (typographic fidelity).
    expect(screen.getByRole("heading", { name: "Chapter One" })).toBeTruthy();
  });

  it("the rich <article> carries data-akb-asset-id for a servable doc (attribution unbroken, §9.0)", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: structuredBlocksJson() }));
    const { container } = await renderReader();
    const article = await waitFor(() => {
      const a = richArticle(container);
      expect(a).toBeTruthy();
      return a as HTMLElement;
    });
    // The SPR-07 attribution marker is present on the rich path for a servable
    // asset — exactly as it was on the legacy ReadingColumn.
    expect(article.getAttribute("data-akb-asset-id")).toBe("doc-1");
    // No fabricated chunk id (asset-level attribution).
    expect(article.getAttribute("data-akb-chunk-id")).toBeNull();
  });

  it("falls back to the legacy ReadingColumn when structured_blocks is NULL", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: null }));
    const { container } = await renderReader();
    // The markdown body renders, but through the legacy column — NO rich
    // data-reader-root article exists.
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    expect(richArticle(container)).toBeNull();
  });

  it("falls back to the legacy flattener when structured_blocks is malformed JSON (degrade, never throw/blank)", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: "{ not valid json" }));
    const { container } = await renderReader();
    await waitFor(() => expect(screen.getByText("The opening of the book.")).toBeTruthy());
    expect(richArticle(container)).toBeNull();
  });

  it("§9.0: a gated book NEVER rich-renders and is NEVER attribution-tagged, even if structured_blocks rode along", async () => {
    // Defense-in-depth: the backend serves structured_blocks null for a withheld
    // body, but even if a stale/poisoned blob were present, the client refuses to
    // rich-render a non-servable book. The gate is servable_full_text=false.
    getBookMock.mockResolvedValue(
      makeDetail({ servability: "gated_metadata_only", servable_full_text: false }),
    );
    getFullTextMock.mockResolvedValue(
      makeBody({
        servable: false,
        full_text: null,
        snippet: "Only a snippet is permitted.",
        ad_eligible: false,
        servability: "gated_metadata_only",
        reason: "gated_metadata_only",
        // A poisoned structured_blocks blob that must NOT be rich-rendered.
        structured_blocks: structuredBlocksJson(),
      }),
    );
    const { container } = await renderReader();
    // The preview notice + snippet render (the legacy snippet path), NOT the rich
    // Reader. The poisoned blocks never reach the DOM.
    await waitFor(() => expect(screen.getByText(/licensed for full reading/)).toBeTruthy());
    expect(screen.getByText("Only a snippet is permitted.")).toBeTruthy();
    // NO rich article, and NOTHING is attribution-tagged for a gated book.
    expect(richArticle(container)).toBeNull();
    expect(container.querySelector("[data-akb-asset-id]")).toBeNull();
    // The poisoned content never rendered.
    expect(screen.queryByText("A richly typeset opening paragraph.")).toBeNull();
  });

  it("the FloatMenu selection scope (articleRef) survives on the rich path — highlighting opens the SAME menu", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: structuredBlocksJson() }));
    await renderReader();
    const para = await screen.findByText("A richly typeset opening paragraph.");
    selectTextIn(para, "A richly typeset opening paragraph.");
    const menu = await screen.findByRole("menu", { name: /Highlight actions/ });
    expect(within(menu).getByRole("menuitem", { name: "Note" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Deep-research" })).toBeTruthy();
  });

  it("LOAD-BEARING (rich path): ad-impression slot count equals the RENDERED page count — no false impressions", async () => {
    // The risk M4 closes: when the rich path paginates by BLOCKS, the page count
    // the pager/usePosition/ad-slots use MUST equal the rendered block-window
    // count. The structured doc has 14 blocks ⇒ 2 windows. A servable non-arXiv
    // doc is ad-eligible, so each rendered page registers top+bottom slots and a
    // page change flushes EXACTLY the previous page's two ad slots — never a
    // slot for a page that didn't render.
    recordAdImpressionsMock.mockClear();
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: structuredBlocksJson() }));
    await renderReader();
    // The pager reports 2 pages (the block-window count), matching the rich render.
    await waitFor(() => expect(screen.getByText(/Page 1 of 2/)).toBeTruthy());
    // Turn the page → the previous (rendered) page's top+bottom ad slots flush.
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    await waitFor(() => expect(screen.getByText(/Page 2 of 2/)).toBeTruthy());
    await waitFor(() => expect(recordAdImpressionsMock).toHaveBeenCalled());
    const flushed = recordAdImpressionsMock.mock.calls.flatMap(([, , items]) =>
      (items as { slot_id: string; page_index: number }[]).map((i) => i),
    );
    // Exactly page-0's top+bottom flushed (page 0 rendered; no slot for a
    // non-existent page). Every flushed slot's page_index is a real rendered page.
    const topBottom = flushed.filter((i) => /:top$|:bottom$/.test(i.slot_id));
    expect(topBottom.map((i) => i.slot_id).sort()).toEqual([
      "slot:doc-1:p0:bottom",
      "slot:doc-1:p0:top",
    ]);
    // No flushed slot references a page index outside the rendered range [0,1].
    expect(flushed.every((i) => i.page_index >= 0 && i.page_index <= 1)).toBe(true);
  });

  it("the derived ToC (rich path) reflects heading blocks and jumps to the right page", async () => {
    getBookMock.mockResolvedValue(makeDetail());
    getFullTextMock.mockResolvedValue(makeBody({ structured_blocks: structuredBlocksJson() }));
    await renderReader();
    const toc = await screen.findByRole("navigation", { name: /Table of contents/ });
    // Two derived entries from the two heading blocks (Chapter One on p0,
    // Chapter Two on p1) — NOT the single legacy book.toc entry ("Chapter 1").
    expect(within(toc).getByRole("button", { name: "Chapter One" })).toBeTruthy();
    const chapterTwo = within(toc).getByRole("button", { name: "Chapter Two" });
    expect(chapterTwo).toBeTruthy();
    // Jumping to Chapter Two (a heading in the 2nd window) moves to page 2.
    fireEvent.click(chapterTwo);
    await waitFor(() => expect(screen.getByText(/Page 2 of 2/)).toBeTruthy());
  });
});
