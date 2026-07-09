import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MarketplaceHost from "./index";

const {
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  fetchAccountLibrary,
  purchaseAndHost,
} = vi.hoisted(() => ({
  fetchMarketplaceCatalog: vi.fn(),
  hostBookIntoAccount: vi.fn(),
  fetchAccountLibrary: vi.fn(),
  purchaseAndHost: vi.fn(),
}));

vi.mock("../../api/marketplaceHost", () => ({
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  fetchAccountLibrary,
  purchaseAndHost,
}));

describe("MarketplaceHost mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchMarketplaceCatalog.mockReset();
    hostBookIntoAccount.mockReset();
    fetchAccountLibrary.mockReset();
    purchaseAndHost.mockReset();
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
      expect(screen.getByText("Modern Systems")).toBeTruthy();
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
