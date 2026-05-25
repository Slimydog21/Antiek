import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor, renderHook, act } from "@testing-library/react";
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
} = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  spinResearchMock: vi.fn(),
  recordAdImpressionsMock: vi.fn().mockResolvedValue(undefined),
  navigateMock: vi.fn(),
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

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

afterEach(() => cleanup());

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
  return {
    document_id: "doc-1",
    servable: true,
    servability: "public_domain",
    full_text: "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.",
    snippet: null,
    title: "A Servable Book",
    author: "Auth",
    reason: "servable",
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
});
