/**
 * sourceDocumentOf — the document a thread was born from (cockpit R3-H3).
 * Three branches, in order: the summary's `document_id` (THREAD-CONTRACT
 * §1.2 ThreadSummary, lane B's W1 wire), else an exact `read-<documentId>`
 * parent, else null. The `read-` ids that name no document are refused.
 */
import { describe, expect, it } from "vitest";

import { sourceDocumentOf } from "./companionStore";

describe("sourceDocumentOf", () => {
  it("branch 1: document_id on the summary wins, whatever the parent", () => {
    expect(sourceDocumentOf({ document_id: "origin-of-species", parent_investigation_id: null })).toBe("origin-of-species");
    expect(sourceDocumentOf({ document_id: "origin-of-species", parent_investigation_id: "read-other-book" })).toBe(
      "origin-of-species",
    );
    expect(sourceDocumentOf({ document_id: "  doc-7  ", parent_investigation_id: "read-spin" })).toBe("doc-7");
  });

  it("branch 2: absent (or blank) document_id falls back to an exact read-<documentId> parent", () => {
    expect(sourceDocumentOf({ parent_investigation_id: "read-voyage-of-the-beagle" })).toBe("voyage-of-the-beagle");
    expect(sourceDocumentOf({ document_id: null, parent_investigation_id: "read-doc-9" })).toBe("doc-9");
    expect(sourceDocumentOf({ document_id: "   ", parent_investigation_id: "read-doc-9" })).toBe("doc-9");
  });

  it.each([
    ["read-meta-mr-abc123", "a meta-reading asset"],
    ["read-meta-", "an empty meta-reading id"],
    ["read-session-42", "a reading session"],
    ["read-session-", "an empty reading session id"],
    ["read-spin", "the passage-research default parent"],
    ["read-", "an empty document id"],
  ])("refuses %s (%s)", (parent) => {
    expect(sourceDocumentOf({ parent_investigation_id: parent })).toBeNull();
  });

  it("branch 3: no document_id and no read- parent gives null (no guessed source)", () => {
    expect(sourceDocumentOf(undefined)).toBeNull();
    expect(sourceDocumentOf({ parent_investigation_id: null })).toBeNull();
    expect(sourceDocumentOf({ parent_investigation_id: "inv-parent-1" })).toBeNull();
    expect(sourceDocumentOf({ parent_investigation_id: "reading-list" })).toBeNull();
    expect(sourceDocumentOf({})).toBeNull();
  });
});
