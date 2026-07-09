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
  handoffBookHtmlFileMock,
  reviewBookHtmlConversionMock,
  recordBookHtmlConversionResultMock,
  reviewBookHtmlServeGateMock,
  requestBookHtmlPublicationMock,
  listInvestigationsMock,
  navigateMock,
} = vi.hoisted(() => ({
  listBooksMock: vi.fn(),
  curateBooksMock: vi.fn(),
  requestBookPurchaseMock: vi.fn(),
  preflightBookHtmlImportMock: vi.fn(),
  handoffBookHtmlFileMock: vi.fn(),
  reviewBookHtmlConversionMock: vi.fn(),
  recordBookHtmlConversionResultMock: vi.fn(),
  reviewBookHtmlServeGateMock: vi.fn(),
  requestBookHtmlPublicationMock: vi.fn(),
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
    handoffBookHtmlFile: handoffBookHtmlFileMock,
    reviewBookHtmlConversion: reviewBookHtmlConversionMock,
    recordBookHtmlConversionResult: recordBookHtmlConversionResultMock,
    reviewBookHtmlServeGate: reviewBookHtmlServeGateMock,
    requestBookHtmlPublication: requestBookHtmlPublicationMock,
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
  handoffBookHtmlFileMock.mockReset();
  reviewBookHtmlConversionMock.mockReset();
  recordBookHtmlConversionResultMock.mockReset();
  reviewBookHtmlServeGateMock.mockReset();
  requestBookHtmlPublicationMock.mockReset();
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

  it("preflights through publication request without ingesting, publishing, or serving", async () => {
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
    handoffBookHtmlFileMock.mockResolvedValue({
      handoff_id: "bookhand-safe123",
      status: "ready_for_conversion_review",
      import_preflight_id: "bookimp-safe123",
      file_name: "dream-machine.epub",
      file_format: "epub",
      storage_ref: "operator-vault://books/dream-machine.epub",
      checksum_sha256: "a".repeat(64),
      import_target: "antiek_html",
      storage_ref_recorded: true,
      upload_accepted: false,
      external_call_performed: false,
      file_read_attempted: false,
      conversion_attempted: false,
      ingest_attempted: false,
      graph_mutation_performed: false,
      html_conversion_required: true,
      html_hosting_required: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    reviewBookHtmlConversionMock.mockResolvedValue({
      conversion_review_id: "bookconv-safe123",
      status: "ready_for_explicit_conversion_job",
      handoff_id: "bookhand-safe123",
      import_preflight_id: "bookimp-safe123",
      converter: "pandoc",
      sandbox_profile: "locked_down",
      output_format: "antiek_html",
      storage_ref_read: false,
      file_read_attempted: false,
      conversion_attempted: false,
      output_written: false,
      ingest_attempted: false,
      graph_mutation_performed: false,
      html_hosting_required: true,
      serve_gate_required: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    recordBookHtmlConversionResultMock.mockResolvedValue({
      conversion_result_id: "bookout-safe123",
      status: "ready_for_serve_gate_review",
      conversion_review_id: "bookconv-safe123",
      handoff_id: "bookhand-safe123",
      html_output_ref: "operator-vault://books/dream-machine/index.html",
      html_checksum_sha256: "b".repeat(64),
      page_count_estimate: 340,
      import_target: "antiek_html",
      output_metadata_recorded: true,
      output_ref_fetched: false,
      html_output_read: false,
      ingest_attempted: false,
      graph_mutation_performed: false,
      shelf_publication_attempted: false,
      full_text_served: false,
      serve_gate_required: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    reviewBookHtmlServeGateMock.mockResolvedValue({
      serve_gate_review_id: "bookserve-safe123",
      status: "ready_for_publication_request",
      conversion_result_id: "bookout-safe123",
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      rights_basis: "personal_license",
      servability_decision: "servable_full_text",
      import_target: "antiek_html",
      rights_review_recorded: true,
      html_output_read: false,
      ingest_attempted: false,
      graph_mutation_performed: false,
      shelf_publication_attempted: false,
      full_text_served: false,
      publication_allowed_next: true,
      required_operator_steps: [],
      policy_notes: [],
    });
    requestBookHtmlPublicationMock.mockResolvedValue({
      publication_request_id: "bookpub-safe123",
      status: "ready_for_explicit_publish_job",
      serve_gate_review_id: "bookserve-safe123",
      conversion_result_id: "bookout-safe123",
      document_id_hint: "book-dream-machine",
      shelf_visibility: "private_library",
      import_target: "antiek_html",
      publication_intent_recorded: true,
      ingest_attempted: false,
      graph_mutation_performed: false,
      shelf_publication_attempted: false,
      full_text_served: false,
      reader_route_created: false,
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

    fireEvent.change(screen.getByLabelText("Storage reference"), {
      target: { value: "operator-vault://books/dream-machine.epub" },
    });
    fireEvent.change(screen.getByLabelText("SHA-256"), {
      target: { value: "a".repeat(64) },
    });
    fireEvent.click(screen.getByLabelText(/manual storage reference/));
    fireEvent.click(screen.getByLabelText(/No file open, read/));
    fireEvent.click(screen.getByRole("button", { name: "Record handoff" }));

    const handoffStatus = await screen.findByText(/Handoff bookhand-safe123/);
    expect(handoffStatus.textContent).toContain("file read no");
    expect(handoffStatus.textContent).toContain("converted no");
    expect(handoffStatus.textContent).toContain("uploaded no");
    expect(handoffBookHtmlFileMock).toHaveBeenCalledWith({
      import_preflight_id: "bookimp-safe123",
      file_name: "dream-machine.epub",
      file_format: "epub",
      storage_ref: "operator-vault://books/dream-machine.epub",
      checksum_sha256: "a".repeat(64),
      acknowledge_manual_storage_only: true,
      acknowledge_no_file_read_or_conversion: true,
    });

    fireEvent.change(screen.getByLabelText("Converter"), {
      target: { value: "pandoc" },
    });
    fireEvent.change(screen.getByLabelText("Sandbox"), {
      target: { value: "locked_down" },
    });
    fireEvent.click(screen.getByLabelText(/converter must run later/));
    fireEvent.click(screen.getByLabelText(/No conversion, file read/));
    fireEvent.click(screen.getByRole("button", { name: "Review conversion" }));

    const conversionStatus = await screen.findByText(/Conversion bookconv-safe123/);
    expect(conversionStatus.textContent).toContain("read no");
    expect(conversionStatus.textContent).toContain("converted no");
    expect(conversionStatus.textContent).toContain("output written no");
    expect(reviewBookHtmlConversionMock).toHaveBeenCalledWith({
      handoff_id: "bookhand-safe123",
      import_preflight_id: "bookimp-safe123",
      converter: "pandoc",
      sandbox_profile: "locked_down",
      output_format: "antiek_html",
      acknowledge_sandbox_required: true,
      acknowledge_no_conversion_run: true,
    });

    fireEvent.change(screen.getByLabelText("HTML output reference"), {
      target: { value: "operator-vault://books/dream-machine/index.html" },
    });
    fireEvent.change(screen.getByLabelText("HTML SHA-256"), {
      target: { value: "b".repeat(64) },
    });
    fireEvent.change(screen.getByLabelText("Pages"), {
      target: { value: "340" },
    });
    fireEvent.click(screen.getByLabelText(/converted-output metadata only/));
    fireEvent.click(screen.getByLabelText(/No output fetch, ingest/));
    fireEvent.click(screen.getByRole("button", { name: "Record output" }));

    const outputStatus = await screen.findByText(/Output bookout-safe123/);
    expect(outputStatus.textContent).toContain("fetched no");
    expect(outputStatus.textContent).toContain("ingested no");
    expect(outputStatus.textContent).toContain("served no");
    expect(recordBookHtmlConversionResultMock).toHaveBeenCalledWith({
      conversion_review_id: "bookconv-safe123",
      handoff_id: "bookhand-safe123",
      html_output_ref: "operator-vault://books/dream-machine/index.html",
      html_checksum_sha256: "b".repeat(64),
      page_count_estimate: 340,
      acknowledge_output_metadata_only: true,
      acknowledge_no_publish_or_serve: true,
    });

    fireEvent.change(screen.getByLabelText("Rights basis"), {
      target: { value: "personal_license" },
    });
    fireEvent.change(screen.getByLabelText("Servability"), {
      target: { value: "servable_full_text" },
    });
    fireEvent.click(screen.getByLabelText(/reviewed rights and servability/));
    fireEvent.click(screen.getByLabelText(/No ingest, graph write/));
    fireEvent.click(screen.getByRole("button", { name: "Review serve gate" }));

    const serveStatus = await screen.findByText(/Serve gate bookserve-safe123/);
    expect(serveStatus.textContent).toContain("ready for publication request");
    expect(serveStatus.textContent).toContain("published no");
    expect(serveStatus.textContent).toContain("served no");
    expect(reviewBookHtmlServeGateMock).toHaveBeenCalledWith({
      conversion_result_id: "bookout-safe123",
      title: "The Dream Machine",
      author: "M. Mitchell Waldrop",
      rights_basis: "personal_license",
      servability_decision: "servable_full_text",
      acknowledge_rights_reviewed: true,
      acknowledge_no_publication: true,
    });

    fireEvent.change(screen.getByLabelText("Document id hint"), {
      target: { value: "book-dream-machine" },
    });
    fireEvent.change(screen.getByLabelText("Visibility"), {
      target: { value: "private_library" },
    });
    fireEvent.click(screen.getByLabelText(/intend to publish/));
    fireEvent.click(screen.getAllByLabelText(/No ingest, graph write, shelf publication/).at(-1)!);
    fireEvent.click(screen.getByRole("button", { name: "Prepare publication" }));

    const publicationStatus = await screen.findByText(/Publication bookpub-safe123/);
    expect(publicationStatus.textContent).toContain("ingested no");
    expect(publicationStatus.textContent).toContain("published no");
    expect(publicationStatus.textContent).toContain("served no");
    expect(requestBookHtmlPublicationMock).toHaveBeenCalledWith({
      serve_gate_review_id: "bookserve-safe123",
      conversion_result_id: "bookout-safe123",
      document_id_hint: "book-dream-machine",
      shelf_visibility: "private_library",
      acknowledge_publication_intent: true,
      acknowledge_no_ingest_or_serve: true,
    });
  });
});
