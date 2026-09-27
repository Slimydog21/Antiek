import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { useEffect } from "react";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { WindowHostProvider } from "../../components/windows/windowHostContext";
import {
  clearReadingFocus,
  formatReadingFocusSystemContext,
  getReadingFocus,
} from "../../lib/readingFocus";
import BookReader from ".";

/**
 * The Thought Partner's reading focus must name the document whose body it
 * carries. BookReader stays mounted across /read/A → /read/B, so a focus built
 * from the previous book's state would hand the model A's page under B's id
 * with a "rights-clean page mount" header (audit W22).
 */

const { getBookMock, getFullTextMock, listBooksMock, useInvestigationMock } = vi.hoisted(() => ({
  getBookMock: vi.fn(),
  getFullTextMock: vi.fn(),
  listBooksMock: vi.fn(),
  useInvestigationMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    getBook: getBookMock,
    getBookFullText: getFullTextMock,
    listBooks: listBooksMock,
    recordAdImpressions: vi.fn().mockResolvedValue(undefined),
  };
});
vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: () => Promise.resolve({ event_id: "ev", action_type: "x" }),
    apiFetch: () => Promise.resolve(new Response("{}", { status: 200 })),
  };
});
vi.mock("../../hooks/useInvestigation", () => ({ useInvestigation: useInvestigationMock }));

const A_TEXT = "## Page 1\n\nALPHA-PAGE-ONE of servable A.\n\n## Page 2\n\nALPHA-PAGE-TWO of servable A.";

function detail(id: string, servable = true): BookDetail {
  return {
    document_id: id,
    title: `Title ${id}`,
    author: "x",
    servability: servable ? "public_domain" : "gated_metadata_only",
    servable_full_text: servable,
    page_count: 2,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
    pagination_scheme: "pdf_page",
    provenance: null,
    license_basis: null,
    toc: [],
  };
}

function body(id: string, servable = true): FullTextResponse {
  return {
    document_id: id,
    servable,
    servability: servable ? "public_domain" : "gated_metadata_only",
    full_text: servable ? A_TEXT : null,
    snippet: servable ? null : "BRAVO gated snippet",
    title: `Title ${id}`,
    author: "x",
    reason: servable ? "servable" : "gated",
    tier: null,
    ad_eligible: servable,
    canonical_url: null,
    license: null,
  };
}

let nav: (to: string) => void = () => {};
function NavGrab() {
  const n = useNavigate();
  useEffect(() => {
    nav = n;
  }, [n]);
  return null;
}

function renderRoute(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <NavGrab />
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getBookMock.mockReset();
  getFullTextMock.mockReset();
  listBooksMock.mockReset();
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  useInvestigationMock.mockReturnValue({
    id: "x",
    status: "not_found",
    events: [],
    question: null,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    reconnects: 0,
  });
  try {
    window.sessionStorage.clear();
  } catch {
    /* no storage */
  }
});

afterEach(() => {
  cleanup();
  clearReadingFocus();
});

describe("BookReader reading focus carries only the open document's body", () => {
  it("does not publish book A's page as book B's rights-clean focus when B fails to load", async () => {
    getBookMock.mockImplementation(async (id: string) => {
      if (id === "doc-A") return detail("doc-A");
      throw new Error("book_not_found");
    });
    getFullTextMock.mockImplementation(async (id: string) => {
      if (id === "doc-A") return body("doc-A");
      throw new Error("book_not_found");
    });
    renderRoute("/read/doc-A");
    await screen.findByText(/ALPHA-PAGE-ONE/);
    expect(getReadingFocus()?.pageText).toContain("ALPHA-PAGE-ONE");

    act(() => nav("/read/doc-B"));
    await screen.findByText("That book isn't in the library.");

    const focus = getReadingFocus();
    expect(focus?.documentId).toBe("doc-B");
    expect(focus?.servable).toBe(false);
    expect(focus?.pageText ?? null).toBeNull();
    expect(focus?.title ?? null).toBeNull();
    expect(formatReadingFocusSystemContext() ?? "").not.toContain("ALPHA-PAGE-ONE");
  });

  it("never pairs book B's id with book A's page while B is still loading", async () => {
    let releaseB: () => void = () => {};
    getBookMock.mockImplementation(async (id: string) => {
      if (id === "doc-A") return detail("doc-A");
      await new Promise<void>((resolve) => {
        releaseB = resolve;
      });
      return detail("doc-B", false);
    });
    getFullTextMock.mockImplementation(async (id: string) =>
      id === "doc-A" ? body("doc-A") : body("doc-B", false),
    );
    const seen: Array<{ documentId: string; pageText: string | null }> = [];
    const listener = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d) seen.push({ documentId: d.documentId, pageText: d.pageText });
    };
    window.addEventListener("antiek:reading:focus", listener);
    try {
      renderRoute("/read/doc-A");
      await screen.findByText(/ALPHA-PAGE-ONE/);
      act(() => nav("/read/doc-B"));
      await screen.findByText("Opening the book…");
      const focus = getReadingFocus();
      expect(focus?.documentId).toBe("doc-B");
      expect(focus?.pageText ?? null).toBeNull();
      expect(focus?.servable).toBe(false);
      await act(async () => releaseB());
      await screen.findByText(/BRAVO gated snippet/);
    } finally {
      window.removeEventListener("antiek:reading:focus", listener);
    }
    // No focus event, even a transient one, named doc-B with A's text.
    const leaked = seen.filter(
      (f) => f.documentId === "doc-B" && (f.pageText ?? "").includes("ALPHA"),
    );
    expect(leaked).toEqual([]);
  });

  it("fails closed when the gate answers for a different document than the one requested", async () => {
    getBookMock.mockImplementation(async () => detail("doc-A"));
    getFullTextMock.mockImplementation(async () => body("doc-A"));
    renderRoute("/read/doc-B");
    await screen.findByText("book_identity_mismatch");
    expect(screen.queryByText(/ALPHA-PAGE-ONE/)).toBeNull();
    const focus = getReadingFocus();
    expect(focus?.documentId).toBe("doc-B");
    expect(focus?.servable).toBe(false);
    expect(focus?.pageText ?? null).toBeNull();
  });

  it("closing one reader window leaves the other open reader's focus in place", async () => {
    getBookMock.mockImplementation(async (id: string) => detail(id, id === "doc-A"));
    getFullTextMock.mockImplementation(async (id: string) => body(id, id === "doc-A"));
    const both = (
      <MemoryRouter>
        <WindowHostProvider value={true}>
          <div key="B">
            <BookReader documentId="doc-B" />
          </div>
          <div key="A">
            <BookReader documentId="doc-A" />
          </div>
        </WindowHostProvider>
      </MemoryRouter>
    );
    const view = render(both);
    await screen.findByText(/ALPHA-PAGE-ONE/);
    await screen.findByText(/BRAVO gated snippet/);
    await waitFor(() => expect(getReadingFocus()?.documentId).toBe("doc-A"));

    // Close window A; B is still open.
    view.rerender(
      <MemoryRouter>
        <WindowHostProvider value={true}>
          <div key="B">
            <BookReader documentId="doc-B" />
          </div>
        </WindowHostProvider>
      </MemoryRouter>,
    );
    const focus = getReadingFocus();
    expect(focus?.documentId).toBe("doc-B");
    expect(focus?.servable).toBe(false);
    expect(focus?.pageText ?? null).toBeNull();
  });
});
