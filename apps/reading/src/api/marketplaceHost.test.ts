import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  purchaseAndHost,
} from "./marketplaceHost";

const mockFetch = vi.fn();

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => mockFetch(...args),
}));

describe("marketplaceHost client", () => {
  beforeEach(() => mockFetch.mockReset());

  it("fetchMarketplaceCatalog", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        entries: [{ book_id: "pd-pride", title: "Pride", author: "A", license_class: "public_domain", is_free: true, source: "se" }],
        count: 1,
        view_format: "html",
      }),
    });
    const out = await fetchMarketplaceCatalog();
    expect(out.count).toBe(1);
    expect(out.view_format).toBe("html");
  });

  it("hostBookIntoAccount posts host", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        document_id: "hdoc_1",
        owner_id: "u",
        book_id: "pd-pride",
        content_hash: "abc",
        title: "Pride",
        license_class: "public_domain",
        already_hosted: false,
        source_format: "html",
        library_document_ids: ["hdoc_1"],
        view_format: "html",
        html: "<p>Pride</p>",
      }),
    });
    const out = await hostBookIntoAccount({
      owner_id: "u",
      book_id: "pd-pride",
    });
    expect(out.document_id).toBe("hdoc_1");
    expect(out.view_format).toBe("html");
    expect(mockFetch).toHaveBeenCalledWith(
      "/marketplace/host",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("purchaseAndHost posts purchase-and-host", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        document_id: "hdoc_2",
        owner_id: "u",
        book_id: "buy-modern",
        content_hash: "def",
        title: "Modern",
        license_class: "purchased",
        already_hosted: false,
        source_format: "pdf",
        library_document_ids: ["hdoc_2"],
        view_format: "html",
        html: "<p>hosted</p>",
        receipt_id: "rcpt_1",
      }),
    });
    const out = await purchaseAndHost({
      owner_id: "u",
      book_id: "buy-modern",
      opaque_reference: "ORDER-1",
      content_b64: "JVBERi0=",
    });
    expect(out.receipt_id).toBe("rcpt_1");
  });
});
