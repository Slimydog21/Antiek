import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import { artifactVersionUrl, deleteStyle, getArtifactStatus, renderArtifact, renderDocument } from "./styles";

const HASH = "9".repeat(64);
const SOURCE_HASH = "8".repeat(64);
function response(headers: Record<string, string>) {
  return new Response("<html></html>", { headers });
}

describe("style artifact receipt contract", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("accepts only an exact durable receipt", async () => {
    apiFetchMock.mockResolvedValue(response({
      "X-Artifact-ID": "inv-1", "X-Artifact-Style": "folio",
      "X-Artifact-Version": "2", "X-Content-SHA256": HASH,
      "X-Source-SHA256": SOURCE_HASH,
    }));
    await expect(renderArtifact("inv-1", "folio", true)).resolves.toMatchObject({ artifactId: "inv-1", style: "folio", version: "2", hash: HASH, sourceHash: SOURCE_HASH });
  });

  it.each([
    ["missing headers", { "X-Artifact-ID": "inv-1" }],
    ["artifact mismatch", { "X-Artifact-ID": "other", "X-Artifact-Style": "folio", "X-Artifact-Version": "2", "X-Content-SHA256": HASH }],
    ["style mismatch", { "X-Artifact-ID": "inv-1", "X-Artifact-Style": "other", "X-Artifact-Version": "2", "X-Content-SHA256": HASH }],
    ["non-positive version", { "X-Artifact-ID": "inv-1", "X-Artifact-Style": "folio", "X-Artifact-Version": "0", "X-Content-SHA256": HASH }],
    ["malformed hash", { "X-Artifact-ID": "inv-1", "X-Artifact-Style": "folio", "X-Artifact-Version": "2", "X-Content-SHA256": "abc" }],
  ])("refuses %s", async (_label, headers) => {
    apiFetchMock.mockResolvedValue(response(headers));
    await expect(renderArtifact("inv-1", "folio", true)).rejects.toThrow("invalid or mismatched artifact receipt");
  });

  it("builds encoded exact and latest routes", () => {
    expect(artifactVersionUrl("inv one", "3")).toBe("/artifacts/inv%20one/versions/3");
    expect(artifactVersionUrl("inv one")).toBe("/artifacts/inv%20one/versions/latest");
  });

  it("loads authoritative investigation identity and treats 404 as absent", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      artifact_id: "artifact-real", investigation_id: "inv-1",
      selected_style: "folio", latest_version: 4,
    }), { headers: { "Content-Type": "application/json" } }));
    await expect(getArtifactStatus("inv-1")).resolves.toMatchObject({ artifact_id: "artifact-real", selected_style: "folio", latest_version: 4 });
    apiFetchMock.mockResolvedValueOnce(new Response("", { status: 404 }));
    await expect(getArtifactStatus("inv-missing")).resolves.toBeNull();
  });

  it("deletes a fork via DELETE /styles/{name} and surfaces HTTP errors", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(deleteStyle("field-notes")).resolves.toBeUndefined();
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/styles/field-notes",
      expect.objectContaining({ method: "DELETE" }),
    );

    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "cannot remove builtin style 'antiek'" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(deleteStyle("antiek")).rejects.toThrow("cannot remove builtin");
  });
});

describe("document render receipt contract", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("builds the documents render route and accepts an exact receipt", async () => {
    apiFetchMock.mockResolvedValue(response({
      "X-Document-ID": "doc one", "X-Artifact-Style": "book",
      "X-Content-SHA256": HASH, "X-Reader-Revision": "3",
    }));
    await expect(renderDocument("doc one", "book")).resolves.toMatchObject({
      documentId: "doc one", style: "book", hash: HASH, readerRevision: "3",
    });
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/documents/doc%20one/render?style=book",
      expect.objectContaining({ signal: undefined }),
    );
  });

  it.each([
    ["missing headers", { "X-Document-ID": "doc-1" }],
    ["document mismatch", { "X-Document-ID": "other", "X-Artifact-Style": "book", "X-Content-SHA256": HASH }],
    ["style mismatch", { "X-Document-ID": "doc-1", "X-Artifact-Style": "other", "X-Content-SHA256": HASH }],
    ["malformed hash", { "X-Document-ID": "doc-1", "X-Artifact-Style": "book", "X-Content-SHA256": "abc" }],
  ])("refuses %s", async (_label, headers) => {
    apiFetchMock.mockResolvedValue(response(headers));
    await expect(renderDocument("doc-1", "book")).rejects.toThrow("invalid or mismatched document receipt");
  });

  it("surfaces the serve gate's refusal reason verbatim", async () => {
    apiFetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "sanitizer_version_stale" }), {
      status: 422, headers: { "Content-Type": "application/json" },
    }));
    await expect(renderDocument("doc-1", undefined)).rejects.toThrow("sanitizer_version_stale");
    expect(apiFetchMock).toHaveBeenCalledWith("/documents/doc-1/render", expect.anything());
  });
});
