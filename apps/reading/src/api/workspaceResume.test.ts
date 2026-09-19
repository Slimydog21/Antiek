import { beforeEach, describe, expect, it, vi } from "vitest";

import { getWorkspaceResume, parseWorkspaceCheckpoint, putWorkspaceResume } from "./workspaceResume";

describe("workspace resume API is strict", () => {
  beforeEach(() => vi.restoreAllMocks());

  it.each([
    { schema_version: 1, revision: 0, entries: [], extra: true },
    { schema_version: 2, revision: 0, entries: [] },
    { schema_version: 1, revision: 0, entries: [{ kind: "stats", title: "leak" }] },
    { schema_version: 1, revision: 0, entries: [{ kind: "hosted_html_document" }] },
    { schema_version: 1, revision: 0, entries: [{ kind: "stats" }, { kind: "stats" }] },
  ])("rejects malformed/open response %#", (body) => {
    expect(() => parseWorkspaceCheckpoint(body)).toThrow();
  });

  it("parses the exact closed response", () => {
    expect(parseWorkspaceCheckpoint({ schema_version: 1, revision: 3, entries: [{ kind: "subaction", workflow: "read" }] })).toEqual({ schema_version: 1, revision: 3, entries: [{ kind: "subaction", workflow: "read" }] });
  });

  it("parses only the four-key ancestry interrogation reference", () => {
    const entry = { kind: "ancestry_interrogation", investigation_id: "inv", manifest_id: "manifest", receipt_id: "receipt" } as const;
    expect(parseWorkspaceCheckpoint({ schema_version: 1, revision: 3, entries: [entry] }).entries).toEqual([entry]);
    expect(() => parseWorkspaceCheckpoint({ schema_version: 1, revision: 3, entries: [{ ...entry, question: "private" }] })).toThrow();
    expect(() => parseWorkspaceCheckpoint({ schema_version: 1, revision: 3, entries: [{ ...entry, receipt_id: "bad\nreceipt" }] })).toThrow();
  });

  it("keeps the same document ID distinct across the two closed resolvers", () => {
    expect(parseWorkspaceCheckpoint({
      schema_version: 1,
      revision: 4,
      entries: [
        { kind: "hosted_html_document", resolver: "hosted_document", document_id: "same" },
        { kind: "hosted_html_document", resolver: "engagement_document", document_id: "same" },
      ],
    }).entries).toEqual([
      { kind: "hosted_html_document", resolver: "hosted_document", document_id: "same" },
      { kind: "hosted_html_document", resolver: "engagement_document", document_id: "same" },
    ]);
    expect(() => parseWorkspaceCheckpoint({
      schema_version: 1,
      revision: 4,
      entries: [{
        kind: "hosted_html_document",
        resolver: "hosted_document",
        document_id: "same\u0000id",
      }],
    })).toThrow();
  });

  it("uses authenticated no-store GET and exact PUT", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 1, revision: 0, entries: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "synced", revision: 1, event_id: "evt-1" }), { status: 200 }));
    await getWorkspaceResume();
    await putWorkspaceResume({ schema_version: 1, base_revision: 0, entries: [{ kind: "stats" }], mutation_key: "stable" });
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: "include", cache: "no-store" });
    expect(fetch.mock.calls[1][1]).toMatchObject({ method: "PUT", credentials: "include", cache: "no-store" });
    expect(JSON.parse(String((fetch.mock.calls[1][1] as RequestInit).body))).toEqual({ schema_version: 1, base_revision: 0, entries: [{ kind: "stats" }], mutation_key: "stable" });
  });
});
