import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../../api/books";
import type { InvestigationSummary } from "../../lib/api";
import BookCard from "./BookCard";
import Library from "./index";
import { WindowHostProvider } from "../../components/windows/windowHostContext";

// Hoisted mocks so the static `import Library` above binds to them.
const {
  listBooksMock,
  curateBooksMock,
  requestBookPurchaseMock,
  preflightBookHtmlImportMock,
  listInvestigationsMock,
  navigateMock,
} = vi.hoisted(() => ({
  listBooksMock: vi.fn(),
  curateBooksMock: vi.fn(),
  requestBookPurchaseMock: vi.fn(),
  preflightBookHtmlImportMock: vi.fn(),
  // M1: the active-research signal documentsByTheme ranks the shelf to.
  // Default: no active research → the feed falls back to recency.
  listInvestigationsMock: vi.fn<
    () => Promise<{ count: number; investigations: InvestigationSummary[] }>
  >(),
  navigateMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    listBooks: listBooksMock,
    curateBooks: curateBooksMock,
    requestBookPurchase: requestBookPurchaseMock,
    preflightBookHtmlImport: preflightBookHtmlImportMock,
  };
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
  requestBookPurchaseMock.mockReset();
  preflightBookHtmlImportMock.mockReset();
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

  it("prepares a no-spend book acquisition request from the Library surface", async () => {
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
    requestBookPurchaseMock.mockResolvedValue({
      request_id: "bookreq-safe123",
      status: "needs_operator_purchase",
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      store: "other",
      source_url: "https://example.com/book",
      max_price_usd_cents: 2500,
      desired_format: "unknown",
      import_target: "antiek_html",
      purchase_allowed: false,
      external_call_performed: false,
      spend_reserved_usd_cents: 0,
      charge_attempted: false,
      ingest_attempted: false,
      html_hosting_required: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );

    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "The Dream Machine" },
    });
    fireEvent.change(screen.getByLabelText("Author"), {
      target: { value: "M. Mitchell Waldrop" },
    });
    fireEvent.change(screen.getByLabelText("Source URL"), {
      target: { value: "https://example.com/book" },
    });
    fireEvent.change(screen.getByLabelText("Max USD"), {
      target: { value: "25" },
    });
    fireEvent.click(screen.getByLabelText(/No purchase, fetch/));
    fireEvent.click(screen.getByRole("button", { name: "Prepare request" }));

    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("bookreq-safe123"));
    expect(requestBookPurchaseMock).toHaveBeenCalledWith({
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      source_url: "https://example.com/book",
      store: "other",
      max_price_usd_cents: 2500,
      desired_format: "unknown",
      import_target: "antiek_html",
      acknowledge_manual_purchase_only: true,
    });
  });

  it("preflights a legally held book file for later Antiek HTML import without uploading or ingesting", async () => {
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
    requestBookPurchaseMock.mockResolvedValue({
      request_id: "bookreq-safe123",
      status: "needs_operator_purchase",
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      store: "other",
      source_url: null,
      max_price_usd_cents: 2500,
      desired_format: "unknown",
      import_target: "antiek_html",
      purchase_allowed: false,
      external_call_performed: false,
      spend_reserved_usd_cents: 0,
      charge_attempted: false,
      ingest_attempted: false,
      html_hosting_required: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    preflightBookHtmlImportMock.mockResolvedValue({
      import_preflight_id: "bookimp-safe123",
      status: "ready_for_operator_file",
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      source_request_id: "bookreq-safe123",
      file_name: "dream-machine.epub",
      file_format: "epub",
      import_target: "antiek_html",
      external_call_performed: false,
      file_uploaded: false,
      file_read_attempted: false,
      ingest_attempted: false,
      graph_mutation_performed: false,
      html_conversion_required: true,
      html_hosting_required: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );

    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "The Dream Machine" },
    });
    fireEvent.change(screen.getByLabelText("Author"), {
      target: { value: "M. Mitchell Waldrop" },
    });
    fireEvent.click(screen.getByLabelText(/No purchase, fetch/));
    fireEvent.click(screen.getByRole("button", { name: "Prepare request" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("bookreq-safe123"));

    fireEvent.change(screen.getByLabelText("File name"), {
      target: { value: "dream-machine.epub" },
    });
    fireEvent.change(screen.getByLabelText("Format"), {
      target: { value: "epub" },
    });
    fireEvent.click(screen.getByLabelText(/I have legal access/));
    fireEvent.click(screen.getByLabelText(/No upload, file read/));
    fireEvent.click(screen.getByRole("button", { name: "Check import" }));

    const importStatus = await screen.findByText(/Import bookimp-safe123/);
    expect(importStatus.textContent).toContain("uploaded no");
    expect(importStatus.textContent).toContain("ingested no");
    expect(preflightBookHtmlImportMock).toHaveBeenCalledWith({
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      source_request_id: "bookreq-safe123",
      file_name: "dream-machine.epub",
      file_format: "epub",
      has_legal_access: true,
      acknowledge_no_upload_or_ingest: true,
    });
  });
});
