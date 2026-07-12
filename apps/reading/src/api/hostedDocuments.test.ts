import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "http://api.test",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import { fetchHostedDocument, ingestHostedDocument } from "./hostedDocuments";

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
    });
    expect(result.document_id).toBe("hdoc_1");
    expect(apiFetch).toHaveBeenCalledWith(
      "http://api.test/hosted-documents/ingest",
      expect.objectContaining({ method: "POST" }),
    );
    const request = vi.mocked(apiFetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual(
      expect.objectContaining({ investigation_id: "inv", source_format: "pdf" }),
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
});
