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
        entries: [
          {
            book_id: "pd-pride",
            title: "Pride",
            author: "A",
            license_class: "public_domain",
            is_free: true,
            source: "se",
            subjects: ["literature"],
          },
        ],
        count: 1,
        view_format: "html",
        // Residual (it/iq/lw): honesty fields from catalog route.
        by_source: { se: 1 },
        by_subject: { literature: 1 },
        public_domain_count: 1,
        purchased_count: 0,
        free_count: 1,
        payment_rails: "manual_receipt_only",
        html: "<html><body>catalog</body></html>",
      }),
    });
    const out = await fetchMarketplaceCatalog();
    expect(out.count).toBe(1);
    expect(out.view_format).toBe("html");
    expect(out.by_source?.se).toBe(1);
    expect(out.by_subject?.literature).toBe(1);
    expect(out.entries[0]?.subjects).toEqual(["literature"]);
    expect(out.public_domain_count).toBe(1);
    expect(out.free_count).toBe(1);
    expect(out.payment_rails).toBe("manual_receipt_only");
    expect(out.html).toContain("catalog");
  });

  it("fetchMarketplaceCatalog passes filter query params (ly)", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        entries: [],
        count: 0,
        view_format: "html",
        html: "<html></html>",
      }),
    });
    await fetchMarketplaceCatalog({
      freeOnly: true,
      subject: "science",
      source: "project_gutenberg",
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringMatching(
        /\/marketplace\/catalog\?.*free_only=true.*subject=science.*source=project_gutenberg/,
      ),
    );
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
