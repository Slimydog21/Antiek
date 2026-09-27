/**
 * Every servabilityLabel consumer renders a personal_readable book (FFX SPR-02
 * M2, finding A-01). Before the fix the reader threw "Cannot destructure
 * property 'label' of 'servabilityLabel(...)'" and blanked the app; BookCard
 * and WorkCard make the same call.
 *
 * Lives next to books.ts rather than under modes/Reading/ because that
 * directory belongs to another lane; the harness mirrors Reading.test.tsx
 * (mock at the api boundary, real components otherwise).
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookDetail, BookSummary, FullTextResponse, Servability } from "./books";
import BookCard from "../modes/Library/BookCard";
import { WITHHELD_OUTBOUND_REASON } from "../modes/shared/FloatMenu/floatMenuActions";
import { getReadingFocus } from "../lib/readingFocus";
import WorkCard from "../components/library/WorkCard";

const { getBookMock, getFullTextMock, listBooksMock, useInvestigationMock, getAnchorMapMock, searchBlocksMock } = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getAnchorMapMock: vi.fn(),
  searchBlocksMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  useInvestigationMock: vi.fn(),
}));

vi.mock("./books", async (orig) => {
  const actual = await orig<typeof import("./books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
    recordAdImpressions: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return {
    ...actual,
    getAnchorMap: getAnchorMapMock,
    searchBlocks: searchBlocksMock,
    apiFetch: vi.fn(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))),
  };
});

vi.mock("../hooks/useInvestigation", () => ({ useInvestigation: useInvestigationMock }));

afterEach(cleanup);

const personal: BookSummary = {
  document_id: "doc-upload-24e63b6fb9eea860",
  title: "Field notes on spaced repetition",
  author: null,
  servability: "personal_readable",
  servable_full_text: false,
  page_count: 1,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

describe("cards render a personal_readable book", () => {
  it("BookCard shows the personal badge, not a platform one", () => {
    render(<BookCard book={personal} />);
    expect(screen.getByText("Personal reading")).toBeTruthy();
    expect(screen.queryByText(/Antiek original/)).toBeNull();
  });

  it("WorkCard shows the personal badge and source line", () => {
    render(<WorkCard work={personal} />);
    expect(screen.getByText("Personal reading")).toBeTruthy();
    expect(screen.getByText("Your document")).toBeTruthy();
    expect(screen.queryByText(/Antiek original/)).toBeNull();
  });

  it("private authored cards distinguish an owner's document from public platform work", () => {
    const privateWork: BookSummary = { ...personal, servability: "private_authored" };
    render(<BookCard book={privateWork} />);
    render(<WorkCard work={privateWork} />);
    expect(screen.getAllByText("Private authored")).toHaveLength(2);
    expect(screen.getByText("Your private document")).toBeTruthy();
    expect(screen.queryByText("Antiek original")).toBeNull();
  });

  it("both cards survive a servability value this build does not know", () => {
    const unknown = { ...personal, servability: "from_a_newer_backend" as Servability };
    render(<BookCard book={unknown} />);
    render(<WorkCard work={unknown} />);
    expect(screen.getAllByText("Unknown rights").length).toBeGreaterThanOrEqual(2);
  });
});

describe("BookReader renders a personal_readable upload (the A-01 journey)", () => {
  // The Reading mode is a large module graph: its first import takes ~3 s in
  // isolation and over 5 s under a loaded full run. Import it once in a hook
  // with its own budget so the test's timer measures rendering, not loading.
  let BookReader: typeof import("../modes/Reading/index").default;
  beforeAll(async () => {
    BookReader = (await import("../modes/Reading/index")).default;
  }, 60_000);

  beforeEach(() => {
    window.sessionStorage.clear();
    getBookMock.mockReset();
    searchBlocksMock.mockReset();
    getAnchorMapMock.mockReset().mockResolvedValue({ chunks: [], complete: true });
    getFullTextMock.mockReset();
    listBooksMock.mockReset().mockResolvedValue({ books: [], count: 0 });
    useInvestigationMock.mockReset().mockReturnValue({
      id: "read-doc",
      status: "not_found",
      events: [],
      question: null,
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      reconnects: 0,
    });
  });

  it("opens with the owner's full text and the personal badge instead of crashing", async () => {
    const detail: BookDetail = {
      ...personal,
      pagination_scheme: "pdf_page",
      provenance: "sources/upload:md",
      license_basis: "personal_reading",
      toc: [],
    };
    const body: FullTextResponse = {
      document_id: personal.document_id,
      servable: false,
      servability: "personal_readable",
      full_text: "Spacing beats massing for long-term retention.",
      snippet: null,
      title: personal.title,
      author: null,
      reason: "owner_personal_reading",
      tier: null,
      ad_eligible: false,
      canonical_url: null,
      license: null,
      content_format: "text",
    };
    getBookMock.mockResolvedValue(detail);
    getFullTextMock.mockResolvedValue(body);

    render(
      <MemoryRouter initialEntries={[`/read/${personal.document_id}`]}>
        <Routes>
          <Route path="/read/:documentId" element={<BookReader />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId("book-reader-root")).toBeTruthy());
    expect(screen.getByText("Personal reading")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText(/Spacing beats massing for long-term retention\./)).toBeTruthy(),
    );
    // Owner-readable: no "Preview only" banner.
    expect(screen.queryByText(/Preview only/)).toBeNull();
  }, 20_000);

  it.each([
    { status: "private_authored", reason: "owner_private_authored", text: "Private draft stays with its owner.", readable: true },
    { status: "private_authored", reason: "private_authored_withheld", text: null, readable: false },
    { status: "taken_down", reason: "taken_down", text: null, readable: false },
    { status: null, reason: "not_found", text: null, readable: false },
    { status: "private_authored", reason: "owner_private_authored", text: null, readable: false },
  ] as const)("owner response $reason with body $text respects admission and reuse", async ({ status, reason, text, readable }) => {
    const detail: BookDetail = {
      ...personal, servability: status ?? "private_authored", taken_down: status === "taken_down",
      pagination_scheme: "pdf_page", provenance: null, license_basis: null, toc: [],
    };
    const full: FullTextResponse = {
      document_id: personal.document_id, servability: status, servable: false,
      full_text: text, snippet: null, title: personal.title, author: null, reason,
      tier: null, ad_eligible: false, canonical_url: null, license: null,
    };
    getBookMock.mockResolvedValue(detail);
    getFullTextMock.mockResolvedValue(full);
    render(<MemoryRouter><BookReader documentId={personal.document_id} /></MemoryRouter>);
    await screen.findByTestId("book-reader-root");
    if (readable) {
      expect(await screen.findByText("Private draft stays with its owner.")).toBeTruthy();
      expect(screen.queryByText(/Preview only/)).toBeNull();
      await waitFor(() => expect(getAnchorMapMock).toHaveBeenCalledWith(personal.document_id, { owner: true }));
      const passage = screen.getByText("Private draft stays with its owner.");
      const range = document.createRange();
      range.selectNodeContents(passage);
      range.getBoundingClientRect = () => new DOMRect(100, 200, 80, 18);
      const selection = window.getSelection();
      if (!selection) throw new Error("Selection unavailable");
      selection.removeAllRanges();
      selection.addRange(range);
      fireEvent(document, new Event("selectionchange"));
      fireEvent.click(await screen.findByRole("menuitem", { name: "Search" }));
      expect(await screen.findByText(WITHHELD_OUTBOUND_REASON)).toBeTruthy();
      expect(searchBlocksMock).not.toHaveBeenCalled();
      selection.removeAllRanges();
    } else {
      expect(screen.queryByText("Private draft stays with its owner.")).toBeNull();
      expect(getAnchorMapMock).not.toHaveBeenCalled();
    }
    expect(document.querySelector("[data-akb-asset-id]")).toBeNull();
    expect(getReadingFocus()).toMatchObject({ servable: false, pageText: null });
  });

});
