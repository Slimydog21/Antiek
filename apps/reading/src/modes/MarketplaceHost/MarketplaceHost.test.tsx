import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MarketplaceHost from "./index";

const fetchMarketplaceCatalog = vi.fn();
const hostBookIntoAccount = vi.fn();
const fetchAccountLibrary = vi.fn();

vi.mock("../../api/marketplaceHost", () => ({
  fetchMarketplaceCatalog: (...args: unknown[]) => fetchMarketplaceCatalog(...args),
  hostBookIntoAccount: (...args: unknown[]) => hostBookIntoAccount(...args),
  fetchAccountLibrary: (...args: unknown[]) => fetchAccountLibrary(...args),
  purchaseAndHost: vi.fn(),
}));

describe("MarketplaceHost mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchMarketplaceCatalog.mockReset();
    hostBookIntoAccount.mockReset();
    fetchAccountLibrary.mockReset();
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
});
