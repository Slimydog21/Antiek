import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "http://api.test",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import { fetchCitationPosition, fetchHostedDocument, ingestHostedDocument, storeCitationPosition } from "./hostedDocuments";

const receipt = {
  document_id: "hdoc_1",
  owner_id: "owner",
  state: "ready" as const,
  source_byte_hash: "sha256:source",
  canonical_content_hash: "sha256:canonical",
  source_format: "pdf",
  title: "Paper",
  document_loaded_event_id: "evt-1",
  already_hosted: false,
  non_viewable_reason: null,
  view_format: "html" as const,
  html: "<!doctype html><html><body>Paper</body></html>",
  source_event_id: "evt-1",
  author: "Researcher",
  page_count: 4,
  word_count: 800,
  projection_state: "ready" as const,
  projection_hash: "sha256:projection",
  projection_version: "hosted-html-projection-v1",
  extraction_receipt: {
    extractor_version: "hosted-document-extractor-v1",
    source_byte_hash: "sha256:source",
    extracted_content_hash: "sha256:extracted",
    canonical_content_hash: "sha256:canonical",
    source_format: "pdf",
    word_count: 800,
    minimum_viewable_words: 50,
    truncated: false,
    viewable: true,
    non_viewable_reason: null,
  },
};

describe("hosted document API", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("posts bytes to the server-owned ingest boundary", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify(receipt), { status: 200 }),
    );
    const result = await ingestHostedDocument({
      content_b64: "JVBERi0=",
      source_format: "pdf",
      investigation_id: "inv",
      title: "Paper.pdf",
      intent: "user_owned",
    });
    expect(result.document_id).toBe("hdoc_1");
    expect(result.projection_state).toBe("ready");
    expect(result.extraction_receipt.canonical_content_hash).toBe(
      result.canonical_content_hash,
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "http://api.test/hosted-documents/ingest",
      expect.objectContaining({ method: "POST" }),
    );
    const request = vi.mocked(apiFetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual(
      expect.objectContaining({
        investigation_id: "inv",
        source_format: "pdf",
        intent: "user_owned",
      }),
    );
  });

  it("rehydrates server-owned canonical HTML by encoded id", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify(receipt), { status: 200 }),
    );
    const result = await fetchHostedDocument("hdoc/unsafe");
    expect(result.html).toContain("Paper");
    expect(apiFetch).toHaveBeenCalledWith(
      "http://api.test/hosted-documents/hdoc%2Funsafe/html",
      { cache: "no-store" },
    );
  });

  it("requests citation chunks as repeated encoded authority hints", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify(receipt), { status: 200 }),
    );
    await fetchHostedDocument("doc-1", ["chunk/a", "chunk b"]);
    expect(apiFetch).toHaveBeenCalledWith(
      "http://api.test/hosted-documents/doc-1/html?citation_chunk_id=chunk%2Fa&citation_chunk_id=chunk+b",
      { cache: "no-store" },
    );
  });

  it("surfaces non-success responses without treating them as HTML", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "other account" }), { status: 403 }),
    );
    await expect(fetchHostedDocument("hdoc_1")).rejects.toThrow(
      "hosted document API 403",
    );
  });

  it("uses no-store and sends only the bounded durable position command", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "found", index: 2 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "synced", event_id: "evt", index: 2 }), { status: 200 }));
    await fetchCitationPosition("doc/1", "a".repeat(64), 3);
    expect(apiFetch).toHaveBeenNthCalledWith(1,
      `http://api.test/hosted-documents/doc%2F1/citation-position?receipt_sha256=${"a".repeat(64)}&anchor_count=3`,
      { cache: "no-store" },
    );
    const evidence = { receipt_sha256: "a".repeat(64) };
    await storeCitationPosition("doc/1", { citation_evidence: evidence, index: 2, anchor_count: 3, mutation_key: "move-1" });
    const request = vi.mocked(apiFetch).mock.calls[1][1] as RequestInit;
    expect(request).toEqual(expect.objectContaining({ method: "PUT", cache: "no-store" }));
    expect(JSON.parse(String(request.body))).toEqual({ citation_evidence: evidence, index: 2, anchor_count: 3, mutation_key: "move-1" });
    expect(String(request.body)).not.toMatch(/html|source_text|account_id/i);
  });

  it("fails closed on malformed durable position responses", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "found", index: 3 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "synced", event_id: "evt", index: 1 }), { status: 200 }));
    await expect(fetchCitationPosition("doc-1", "a".repeat(64), 3)).rejects.toThrow(
      "invalid citation position",
    );
    await expect(storeCitationPosition("doc-1", {
      citation_evidence: { receipt_sha256: "a".repeat(64) },
      index: 2,
      anchor_count: 3,
      mutation_key: "move-2",
    })).rejects.toThrow("invalid citation position receipt");
  });
});
