import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../../api/books";
import type { InvestigationSummary } from "../../lib/api";
import BookCard from "./BookCard";
import Library from "./index";
import { WindowHostProvider } from "../../components/windows/windowHostContext";

// Hoisted mocks so the static `import Library` above binds to them.
const { listBooksMock, curateBooksMock, listInvestigationsMock, navigateMock } = vi.hoisted(() => ({
  listBooksMock: vi.fn(),
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
  return { ...actual, listBooks: listBooksMock, curateBooks: curateBooksMock };
});

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
  listBooksMock.mockReset();
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

  it("falls back deterministically when a real cover fails", () => {
    const covered = { ...servableBook, cover_uri: "https://example.test/cover.jpg" };
    render(<BookCard book={covered} />);
    const image = screen.getByRole("img", { name: "Cover of Meditations" });
    fireEvent.error(image);
    const fallback = screen.getByTestId("library-fallback-cover");
    expect(fallback.getAttribute("aria-hidden")).toBe("true");
    expect(fallback.parentElement?.getAttribute("data-cover-variant")).toBeTruthy();
    expect(screen.queryByRole("img", { name: "Cover of Meditations" })).toBeNull();
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
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
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
    const environment = screen.getByTestId("library-archive-environment") as HTMLImageElement;
    expect(environment.alt).toBe("");
    expect(environment.getAttribute("aria-hidden")).toBe("true");
    expect(environment.draggable).toBe(false);
    expect(environment.className).toContain("pointer-events-none");
    expect(surface!.contains(environment)).toBe(false);

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
    expect(inWin.queryByTestId("library-archive-environment")).toBeNull();
  });

  it("renders mutually exclusive authored loading and error states with retry", async () => {
    let reject!: (error: Error) => void;
    listBooksMock.mockReturnValue(new Promise((_resolve, rejectPromise) => { reject = rejectPromise; }));
    renderLibrary();
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/Opening the archive/);
    expect(screen.queryByRole("alert")).toBeNull();
    reject(new Error("private backend detail"));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText(/Shelf count unavailable/)).toBeTruthy();
    expect(screen.queryByText(/0 books readable/)).toBeNull();
    expect(screen.queryByText(/Nothing is readable/)).toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/Shelf contents are unavailable/);
    expect(screen.getByRole("alert").textContent).not.toMatch(/unchanged/);
    expect(screen.getByRole("alert").textContent).not.toMatch(/private backend detail/);

    listBooksMock.mockResolvedValueOnce({ books: [servableBook], count: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("button", { name: /Open Meditations/ });
    expect(listBooksMock).toHaveBeenLastCalledWith("servable");
  });

  it("ignores a superseded shelf response after switching to Preview", async () => {
    let resolveShelf!: (value: { books: BookSummary[]; count: number }) => void;
    listBooksMock
      .mockReturnValueOnce(new Promise((resolve) => { resolveShelf = resolve; }))
      .mockResolvedValueOnce({ books: [gatedBook], count: 1 });
    renderLibrary();
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await screen.findByRole("button", { name: /Open A Licensed Title/ });
    resolveShelf({ books: [servableBook], count: 1 });
    await Promise.resolve();
    expect(screen.queryByRole("button", { name: /Open Meditations/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Open A Licensed Title/ })).toBeTruthy();
  });

  it("loads under React StrictMode effect replay", async () => {
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
    render(
      <StrictMode>
        <MemoryRouter><Library /></MemoryRouter>
      </StrictMode>,
    );
    expect(await screen.findByRole("button", { name: /Open Meditations/ })).toBeTruthy();
  });

  it("ignores a stale curation failure after switching shelves", async () => {
    let rejectCurate!: (error: Error) => void;
    listBooksMock
      .mockResolvedValueOnce({ books: [servableBook], count: 1 })
      .mockResolvedValueOnce({ books: [gatedBook], count: 1 })
      .mockResolvedValueOnce({ books: [servableBook], count: 1 });
    curateBooksMock.mockReturnValue(new Promise((_resolve, reject) => { rejectCurate = reject; }));
    renderLibrary();
    await screen.findByRole("button", { name: /Open Meditations/ });
    fireEvent.change(screen.getByLabelText("Curate the library by prompt"), { target: { value: "stoicism" } });
    fireEvent.click(screen.getByRole("button", { name: "Curate" }));
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await screen.findByRole("button", { name: /Open A Licensed Title/ });
    rejectCurate(new Error("stale curation failure"));
    await Promise.resolve();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /Open A Licensed Title/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Shelf" }));
    await screen.findByRole("button", { name: /Open Meditations/ });
    fireEvent.change(screen.getByLabelText("Curate the library by prompt"), { target: { value: "ethics" } });
    const curate = screen.getByRole("button", { name: "Curate" }) as HTMLButtonElement;
    expect(curate.disabled).toBe(false);
  });

  it("loads the servable shelf and routes to the reader on open", async () => {
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    expect(listBooksMock).toHaveBeenCalledWith("servable");
    fireEvent.click(screen.getByRole("button", { name: /Open Meditations/ }));
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-pd");
  });

  it("switching to Preview reloads the gated set", async () => {
    listBooksMock
      .mockResolvedValueOnce({ books: [servableBook], count: 1 })
      .mockResolvedValueOnce({ books: [gatedBook], count: 1 });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open A Licensed Title/ })).toBeTruthy(),
    );
    expect(listBooksMock).toHaveBeenLastCalledWith("gated");
  });

  it("shows an honest empty-state (what's available to read, not an uploader)", async () => {
    listBooksMock.mockResolvedValue({ books: [], count: 0 });
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
    listBooksMock.mockResolvedValue({ books: [novel, stoic], count: 2 });
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
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
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
    listBooksMock.mockResolvedValue({ books: [servableBook, second], count: 2 });
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
