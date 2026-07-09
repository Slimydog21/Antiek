import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MarketplaceHost from "./index";

const {
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  fetchAccountLibrary,
  purchaseAndHost,
  fetchHostedDocumentHtml,
  openWindow,
} = vi.hoisted(() => ({
  fetchMarketplaceCatalog: vi.fn(),
  hostBookIntoAccount: vi.fn(),
  fetchAccountLibrary: vi.fn(),
  purchaseAndHost: vi.fn(),
  fetchHostedDocumentHtml: vi.fn(),
  openWindow: vi.fn(() => "win:hosted:hdoc_abc"),
}));

vi.mock("../../api/marketplaceHost", () => ({
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  fetchAccountLibrary,
  purchaseAndHost,
  fetchHostedDocumentHtml,
}));

vi.mock("../../components/windows/openWindow", () => ({
  openWindow,
}));

vi.mock("../../components/engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: () => (
    <div data-testid="decision-tree-driver-badge-stub">driver badge</div>
  ),
}));

describe("MarketplaceHost mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchMarketplaceCatalog.mockReset();
    hostBookIntoAccount.mockReset();
    fetchAccountLibrary.mockReset();
    purchaseAndHost.mockReset();
    fetchHostedDocumentHtml.mockReset();
    openWindow.mockClear();
    // Residual (dq): library loads on mount — default empty honest library.
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
  });

  it("loads catalog and hosts public domain book", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 1,
      view_format: "html",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_abc",
      owner_id: "operator",
      book_id: "pd-pride",
      content_hash: "x",
      title: "Pride and Prejudice",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_abc"],
      view_format: "html",
      html: "<p>It is a truth universally acknowledged</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [{ document_id: "hdoc_abc", title: "Pride" }],
      count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    // Residual (dz): decision-tree driver badge on marketplace (reading ≡ research).
    expect(screen.getByTestId("marketplace-driver-badge-mount")).toBeTruthy();
    expect(
      screen
        .getByTestId("marketplace-driver-badge-mount")
        .getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("host-result").textContent).toContain("hdoc_abc");
    });
    expect(hostBookIntoAccount).toHaveBeenCalledWith({
      owner_id: "operator",
      book_id: "pd-pride",
    });
    expect(screen.getByTestId("hosted-html").innerHTML).toContain("truth");
    // Residual (gi): host-result → Write HTML draft handoff.
    const writeLink = screen.getByTestId("marketplace-open-write");
    expect(writeLink.getAttribute("href")).toBe("/write?html_draft=hdoc_abc");
    expect(writeLink.getAttribute("data-view-format")).toBe("html");
    expect(writeLink.getAttribute("data-document-id")).toBe("hdoc_abc");
    // Residual (dk): auto-open hosted window after host (default on).
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "hdoc_abc",
          view_format: "html",
        }),
        expect.objectContaining({ id: "win:hosted:hdoc_abc" }),
      );
    });
    // Residual (dl): structured library list after host.
    await waitFor(() => {
      expect(screen.getByTestId("library-doc-list")).toBeTruthy();
      expect(screen.getByTestId("library-doc-hdoc_abc")).toBeTruthy();
    });
    // Residual (gi): library row → Write handoff.
    const libWrite = screen.getByTestId("library-open-write-hdoc_abc");
    expect(libWrite.getAttribute("href")).toBe("/write?html_draft=hdoc_abc");
    expect(libWrite.getAttribute("data-view-format")).toBe("html");
    expect(screen.getByTestId("library-filter-count").textContent).toMatch(
      /Showing 1 of 1/,
    );
    fireEvent.change(screen.getByTestId("library-filter"), {
      target: { value: "hdoc_abc" },
    });
    expect(screen.getByTestId("library-doc-hdoc_abc")).toBeTruthy();
    fireEvent.change(screen.getByTestId("library-filter"), {
      target: { value: "nope" },
    });
    expect(screen.getByTestId("library-filter-empty")).toBeTruthy();
  });

  it("loads account library on mount and rehydrates open (dq/do)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-x",
          title: "New",
          author: "A",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 1,
      view_format: "html",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [
        {
          document_id: "hdoc_old",
          title: "Old Hosted Book",
          license_class: "public_domain",
          view_format: "html",
        },
      ],
      count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });
    fetchHostedDocumentHtml.mockResolvedValue({
      document_id: "hdoc_old",
      view_format: "html",
      title: "Old Hosted Book",
      license_class: "public_domain",
      html: "<article><h1>Old Hosted Book</h1><p>Rehydrated body.</p></article>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    // Residual (dq): library visible without host first.
    await waitFor(() => {
      expect(fetchAccountLibrary).toHaveBeenCalledWith("operator");
    });
    await waitFor(() => {
      expect(screen.getByTestId("library-doc-hdoc_old")).toBeTruthy();
    });
    openWindow.mockClear();
    fireEvent.click(screen.getByTestId("library-open-hdoc_old"));
    await waitFor(() => {
      expect(fetchHostedDocumentHtml).toHaveBeenCalledWith("hdoc_old");
    });
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "hdoc_old",
          view_format: "html",
          source: "marketplace_library_rehydrate",
        }),
        expect.objectContaining({ id: "win:hosted:hdoc_old" }),
      );
    });
    const payload = openWindow.mock.calls.at(-1)?.[1] as { html?: string };
    expect(payload.html).toMatch(/Rehydrated body/);
  });

  it("filters catalog by title/author substring (dj)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
        {
          book_id: "pd-moby",
          title: "Moby-Dick",
          author: "Herman Melville",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 2,
      view_format: "html",
    });

    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
      expect(screen.getByText("Moby-Dick")).toBeTruthy();
    });
    expect(screen.getByTestId("catalog-filter-count").textContent).toMatch(
      /Showing 2 of 2/,
    );
    fireEvent.change(screen.getByTestId("catalog-filter"), {
      target: { value: "melville" },
    });
    expect(screen.getByTestId("catalog-filter-count").textContent).toMatch(
      /Showing 1 of 2/,
    );
    expect(screen.getByText("Moby-Dick")).toBeTruthy();
    expect(screen.queryByText("Pride and Prejudice")).toBeNull();
    fireEvent.change(screen.getByTestId("catalog-filter"), {
      target: { value: "zzz-no-match" },
    });
    expect(screen.getByTestId("catalog-filter-empty")).toBeTruthy();
  });

  it("opens hosted book in floating HTML window (bt)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 1,
      view_format: "html",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_abc",
      owner_id: "operator",
      book_id: "pd-pride",
      content_hash: "x",
      title: "Pride and Prejudice",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_abc"],
      view_format: "html",
      html: "<p>It is a truth universally acknowledged</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [{ document_id: "hdoc_abc" }],
      count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("open-hosted-in-window")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("open-hosted-in-window"));
    expect(openWindow).toHaveBeenCalled();
    const call = openWindow.mock.calls.at(-1) as unknown as [
      string,
      Record<string, unknown>,
      Record<string, unknown>?,
    ];
    expect(call[0]).toBe("hosted_html_document");
    expect(call[1].document_id).toBe("hdoc_abc");
    expect(call[1].view_format).toBe("html");
    expect(String(call[1].html)).toMatch(/truth/);
  });

  it("purchases and hosts paid catalog title with receipt ref", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "buy-modern",
          title: "Modern Systems",
          author: "Author X",
          license_class: "purchased",
          is_free: false,
          source: "bookstore",
        },
      ],
      count: 1,
      view_format: "html",
    });
    purchaseAndHost.mockResolvedValue({
      document_id: "hdoc_buy",
      owner_id: "operator",
      book_id: "buy-modern",
      content_hash: "y",
      title: "Modern Systems",
      license_class: "purchased",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_buy"],
      view_format: "html",
      html: "<p>Hosted after manual purchase receipt</p>",
      receipt_id: "rcpt_1",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [{ document_id: "hdoc_buy", title: "Modern Systems" }],
      count: 1,
      view_format: "html",
      html: "<p>Library with purchase</p>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      // Catalog purchase button (library may also list "Modern Systems" after mount).
      expect(screen.getByTestId("purchase-host-buy-modern")).toBeTruthy();
    });
    expect(screen.getByTestId("purchase-receipt-ref")).toBeTruthy();
    fireEvent.click(screen.getByTestId("purchase-host-buy-modern"));
    await waitFor(() => {
      expect(purchaseAndHost).toHaveBeenCalled();
    });
    const call = purchaseAndHost.mock.calls.at(-1)?.[0] as {
      owner_id: string;
      book_id: string;
      opaque_reference: string;
      content_b64: string;
    };
    expect(call.owner_id).toBe("operator");
    expect(call.book_id).toBe("buy-modern");
    expect(call.opaque_reference).toBeTruthy();
    expect(call.content_b64).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId("host-result").textContent).toContain("hdoc_buy");
    });
    expect(screen.getByTestId("hosted-html").innerHTML).toMatch(/purchase|Hosted/i);
    expect(
      screen.getByTestId("marketplace-host-mode").getAttribute("data-view-format"),
    ).toBe("html");
  });
});
