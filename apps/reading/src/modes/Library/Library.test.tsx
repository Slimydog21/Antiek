import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../../api/books";
import type { InvestigationSummary } from "../../lib/api";
import BookCard from "./BookCard";
import Library from "./index";
import { WindowHostProvider } from "../../components/windows/windowHostContext";

// Hoisted mocks so the static `import Library` above binds to them.
const { fetchLibraryCatalogMock, curateBooksMock, listInvestigationsMock, navigateMock } = vi.hoisted(() => ({
  fetchLibraryCatalogMock: vi.fn(),
  curateBooksMock: vi.fn(),
  // M1: the active-research signal documentsByTheme ranks the shelf to.
  // Default: no active research → the feed falls back to recency.
  listInvestigationsMock: vi.fn<
    () => Promise<{ count: number; investigations: InvestigationSummary[] }>
  >(),
  navigateMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return { ...actual, curateBooks: curateBooksMock };
});

vi.mock("../../api/libraryCatalog", () => ({
  fetchLibraryCatalog: fetchLibraryCatalogMock,
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, listInvestigations: listInvestigationsMock };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const servableBook: BookSummary = {
  document_id: "doc-pd",
  title: "Meditations",
  author: "Marcus Aurelius",
  servability: "public_domain",
  servable_full_text: true,
  page_count: 254,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

const gatedBook: BookSummary = {
  ...servableBook,
  document_id: "doc-gated",
  title: "A Licensed Title",
  author: "Some Author",
  servability: "gated_metadata_only",
  servable_full_text: false,
};

beforeEach(() => {
  fetchLibraryCatalogMock.mockReset();
  curateBooksMock.mockReset();
  listInvestigationsMock.mockReset();
  listInvestigationsMock.mockResolvedValue({ count: 0, investigations: [] });
  navigateMock.mockReset();
  // The full-page Library landing now renders through GlassSurface (SPR-03 M2
  // landing-glass; the inWindow branch stays bg-transparent), which reads
  // prefers-reduced-motion via window.matchMedia. jsdom lacks it; stub the
  // default (motion allowed → the glass variant renders). Weakens nothing.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});
afterEach(() => cleanup());

describe("BookCard", () => {
  it("renders title, author, and a servability badge", () => {
    render(<BookCard book={servableBook} />);
    // Title is the button's accessible name (the cover spine is decorative).
    expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy();
    expect(screen.getByText(/Marcus Aurelius/)).toBeTruthy();
    expect(screen.getByText("Public domain")).toBeTruthy();
  });

  it("flags a gated book as preview-only (never implies full read)", () => {
    render(<BookCard book={gatedBook} />);
    expect(screen.getByText("Preview only")).toBeTruthy();
  });

  it("calls onOpen with the document id when clicked", () => {
    const onOpen = vi.fn();
    render(<BookCard book={servableBook} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: /Open Meditations/ }));
    expect(onOpen).toHaveBeenCalledWith("doc-pd");
  });

  it("makes taken-down works unavailable and gated works previews", () => {
    const onOpen = vi.fn();
    const { rerender } = render(<BookCard book={gatedBook} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: /Preview A Licensed Title/ }));
    expect(onOpen).toHaveBeenCalledWith("doc-gated");
    rerender(<BookCard book={{ ...gatedBook, servability: "taken_down", taken_down: true }} onOpen={onOpen} />);
    const unavailable = screen.getByRole("button", { name: /Unavailable A Licensed Title/ });
    expect((unavailable as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("Library", () => {
  function renderLibrary() {
    return render(
      <MemoryRouter>
        <Library />
      </MemoryRouter>,
    );
  }

  it("full-page Read door is LANDING-GLASS; the inWindow branch stays bg-transparent (SPR-03 + SPR-09 contracts)", async () => {
    fetchLibraryCatalogMock.mockResolvedValue({ works: [servableBook], total: 1, page: 1, page_size: 20 });
    // Full-page (default useInWindow=false): the Read-door landing renders through
    // GlassSurface so the scene shows through (audit §3 item 4). A refactor back
    // to an opaque body / variant=solid would re-occlude the mountain (rigor #5).
    const { container } = renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "the full-page Library must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");

    cleanup();
    // inWindow: SPR-09 owns the window glass, so the body stays bg-transparent and
    // is NOT re-glassed (no nested GlassSurface, no opaque wall) — the verbatim
    // contract the audit preserves.
    const inWin = render(
      <MemoryRouter>
        <WindowHostProvider value={true}>
          <Library />
        </WindowHostProvider>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(inWin.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    expect(
      inWin.container.querySelector("[data-glass-surface]"),
      "inWindow Library must NOT re-glass the body (SPR-09 host owns the glass)",
    ).toBeNull();
    const mainEl = inWin.container.querySelector("main");
    expect(mainEl?.className).toContain("bg-transparent");
  });

  it("loads the servable shelf and routes to the reader on open", async () => {
    fetchLibraryCatalogMock.mockResolvedValue({ works: [servableBook], total: 1, page: 1, page_size: 20 });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    expect(fetchLibraryCatalogMock).toHaveBeenCalledWith(expect.objectContaining({ filter: "servable" }), expect.any(AbortSignal));
    fireEvent.click(screen.getByRole("button", { name: /Open Meditations/ }));
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-pd");
  });

  it("switching to Preview reloads the gated set", async () => {
    fetchLibraryCatalogMock
      .mockResolvedValueOnce({ works: [servableBook], total: 1, page: 1, page_size: 20 })
      .mockResolvedValueOnce({ works: [gatedBook], total: 1, page: 1, page_size: 20 });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Preview A Licensed Title/ })).toBeTruthy(),
    );
    expect(fetchLibraryCatalogMock).toHaveBeenLastCalledWith(expect.objectContaining({ filter: "gated", page: 1 }), expect.any(AbortSignal));
  });

  it("supports roving keyboard focus across complete catalog tabs", async () => {
    fetchLibraryCatalogMock.mockResolvedValue({ works: [servableBook], total: 1, page: 1, page_size: 20 });
    renderLibrary();
    const shelf = screen.getByRole("tab", { name: "Shelf" });
    shelf.focus();
    fireEvent.keyDown(shelf, { key: "ArrowRight" });
    const preview = screen.getByRole("tab", { name: "Preview" });
    expect(document.activeElement).toBe(preview);
    expect(preview.getAttribute("aria-controls")).toBe("library-catalog-panel");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe("library-tab-gated");
    fireEvent.keyDown(preview, { key: "End" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "All" }));
    expect(shelf.className).toContain("min-h-11");
    expect(screen.getByRole("search").className).toContain("flex-col");
  });

  it("searches title/author explicitly and resets pagination", async () => {
    fetchLibraryCatalogMock.mockResolvedValue({ works: [servableBook], total: 41, page: 1, page_size: 20 });
    renderLibrary();
    await screen.findByRole("button", { name: /Open Meditations/ });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(fetchLibraryCatalogMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }), expect.any(AbortSignal),
    ));
    fireEvent.change(screen.getByRole("searchbox", { name: /title or author/i }), {
      target: { value: "  Aurelius  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search catalog" }));
    await waitFor(() => expect(fetchLibraryCatalogMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: "Aurelius", page: 1, page_size: 20 }), expect.any(AbortSignal),
    ));
  });

  it("recovers once to the last valid page when the catalog shrinks", async () => {
    fetchLibraryCatalogMock
      .mockResolvedValueOnce({ works: [servableBook], total: 21, page: 1, page_size: 20 })
      .mockResolvedValueOnce({ works: [], total: 1, page: 2, page_size: 20 })
      .mockResolvedValueOnce({ works: [servableBook], total: 1, page: 1, page_size: 20 });
    renderLibrary();
    await screen.findByRole("button", { name: /Open Meditations/ });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(fetchLibraryCatalogMock).toHaveBeenCalledTimes(3));
    expect(fetchLibraryCatalogMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1 }), expect.any(AbortSignal),
    );
    await screen.findByText("Page 1 of 1 · 1 titles");
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(fetchLibraryCatalogMock).toHaveBeenCalledTimes(3);
  });

  it("contains a late ancillary rejection after supersession without stale mutation", async () => {
    let rejectResearch!: (reason?: unknown) => void;
    listInvestigationsMock.mockReturnValueOnce(new Promise((_resolve, reject) => {
      rejectResearch = reject;
    }));
    fetchLibraryCatalogMock
      .mockResolvedValueOnce({ works: [servableBook], total: 1, page: 1, page_size: 20 })
      .mockResolvedValueOnce({ works: [gatedBook], total: 1, page: 1, page_size: 20 });
    renderLibrary();
    await screen.findByRole("button", { name: /Open Meditations/ });
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await screen.findByRole("button", { name: /Preview A Licensed Title/ });
    rejectResearch(new Error("private late failure"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByRole("tab", { name: "Preview" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByText(/private late failure/)).toBeNull();
    expect(fetchLibraryCatalogMock).toHaveBeenCalledTimes(2);
  });

  it("contains a late ancillary rejection after unmount", async () => {
    let rejectResearch!: (reason?: unknown) => void;
    listInvestigationsMock.mockReturnValueOnce(new Promise((_resolve, reject) => {
      rejectResearch = reject;
    }));
    fetchLibraryCatalogMock.mockResolvedValueOnce({
      works: [servableBook], total: 1, page: 1, page_size: 20,
    });
    const view = renderLibrary();
    await screen.findByRole("button", { name: /Open Meditations/ });
    view.unmount();
    rejectResearch(new Error("private post-unmount failure"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchLibraryCatalogMock).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).not.toContain("private post-unmount failure");
  });

  it("aborts superseded requests and ignores stale results", async () => {
    let resolveFirst!: (value: { works: BookSummary[]; total: number; page: number; page_size: number }) => void;
    fetchLibraryCatalogMock.mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }));
    fetchLibraryCatalogMock.mockResolvedValueOnce({ works: [gatedBook], total: 1, page: 1, page_size: 20 });
    renderLibrary();
    const firstSignal = fetchLibraryCatalogMock.mock.calls[0][1] as AbortSignal;
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    expect(firstSignal.aborted).toBe(true);
    await screen.findByRole("button", { name: /Preview A Licensed Title/ });
    resolveFirst({ works: [servableBook], total: 1, page: 1, page_size: 20 });
    await Promise.resolve();
    expect(screen.queryByRole("button", { name: /Open Meditations/ })).toBeNull();
  });

  it("shows an honest empty-state (what's available to read, not an uploader)", async () => {
    fetchLibraryCatalogMock.mockResolvedValue({ works: [], total: 0, page: 1, page_size: 20 });
    renderLibrary();
    // Read SPR-06: an empty shelf is honest about the servable corpus — it
    // points to Preview / bring-your-own, never prompts an operator ingest.
    await waitFor(() =>
      expect(screen.getByText(/only shows what can be legally aggregated/)).toBeTruthy(),
    );
    // It is the Read door's honest "nothing to read in full yet" state — not
    // an upload prompt as the home (the wrestler is a demoted side affordance).
    expect(screen.queryByText(/Load a PDF to wrestle/)).toBeNull();
  });

  it("ranks the servable shelf to active research themes and SAYS so (M1 theme ordering)", async () => {
    const stoic = { ...servableBook, document_id: "doc-stoic", title: "A Guide to Stoicism", author: "Anon" };
    const novel = { ...servableBook, document_id: "doc-novel", title: "War and Peace", author: "Tolstoy" };
    fetchLibraryCatalogMock.mockResolvedValue({ works: [novel, stoic], total: 2, page: 1, page_size: 20 });
    const activeInv: InvestigationSummary = {
      investigation_id: "inv-1",
      question: "How does Stoicism shape resilience?",
      status: "in_progress",
      started_at: null,
      completed_at: null,
      cost_usd_total: 0,
      parent_investigation_id: null,
    };
    listInvestigationsMock.mockResolvedValue({ count: 1, investigations: [activeInv] });
    renderLibrary();
    // The honest label states the feed is theme-ranked, and names the theme.
    const label = await screen.findByText(/Ranked to your active research/);
    expect(label.textContent).toMatch(/stoicism/i);
    // The matching book is ordered first (most-relevant).
    const cards = screen.getAllByRole("button", { name: /^Open / });
    expect(cards[0].getAttribute("aria-label")).toMatch(/Stoicism/);
  });

  it("falls back to recency with an HONEST label when there is no active research (thin-signal fallback)", async () => {
    fetchLibraryCatalogMock.mockResolvedValue({ works: [servableBook], total: 1, page: 1, page_size: 20 });
    listInvestigationsMock.mockResolvedValue({ count: 0, investigations: [] });
    renderLibrary();
    // It does not fabricate relevance — it admits it is showing recency.
    await waitFor(() =>
      expect(screen.getByText(/showing the most recently added first/)).toBeTruthy(),
    );
    expect(screen.queryByText(/Ranked to your active research/)).toBeNull();
  });

  it("curates the shelf by prompt, re-ranking to the curated order", async () => {
    const second = { ...servableBook, document_id: "doc-2", title: "Second Book" };
    fetchLibraryCatalogMock.mockResolvedValue({ works: [servableBook, second], total: 2, page: 1, page_size: 20 });
    // Curate returns the two in REVERSE relevance order.
    curateBooksMock.mockResolvedValue({
      prompt: "stoicism",
      books: [
        { document_id: "doc-2", title: "Second Book", author: "A", score: 0.9 },
        { document_id: "doc-pd", title: "Meditations", author: "Marcus Aurelius", score: 0.4 },
      ],
    });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    const input = screen.getByLabelText("Curate the library by prompt");
    fireEvent.change(input, { target: { value: "stoicism" } });
    fireEvent.click(screen.getByRole("button", { name: "Curate" }));
    await waitFor(() => expect(screen.getByText(/Curated for/)).toBeTruthy());
    expect(curateBooksMock).toHaveBeenCalledWith("stoicism");
    // Curated order: Second Book first, Meditations second.
    const cards = screen.getAllByRole("button", { name: /^Open / });
    expect(cards[0].getAttribute("aria-label")).toMatch(/Second Book/);
  });
});
