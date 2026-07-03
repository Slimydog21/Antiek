import { describe, expect, it } from "vitest";

import { buildReadActivationEvidenceDraft } from "./read_activation_evidence";

describe("read activation evidence draft", () => {
  it("builds an explicit non-append-ready record-session template", () => {
    const draft = buildReadActivationEvidenceDraft({
      sessionId: "read-golden-path-e2e-abcdef0",
      date: "2026-07-03",
      buildSha: "abcdef0123456789",
      url: "http://localhost:4173/read/doc-1",
      operator: "operator",
      documentId: "doc-1",
      entryDoor: "library",
      visibleContentNote: "real Reader route rendered Chapter One",
      selectedText: "A cited claim with enough text for selection",
      dialogueNoKeyCopy: "No model provider configured; activation SPR-03.",
      researchNoKeyCopy: "No model provider configured; activation SPR-03.",
      sourceDocumentId: "doc-source-42",
      chunkId: "chunk-7",
      resultUrl:
        "http://localhost:4173/read/doc-source-42?chunk=chunk-7&from=doc-1",
      returnContextNote: "Return control reopened /read/doc-1?page=0",
    });

    expect(draft.schema_version).toBe(1);
    expect(draft.kind).toBe("read_activation_record_session_draft");
    expect(draft.ready_to_append).toBe(false);
    expect(draft.operator_fields_to_replace).toEqual([
      "<minutes_reading_at_least_20>",
      "<operator_20_minute_reading_note>",
    ]);
    expect(draft.record_session_argv_template).toContain("record-session");
    expect(draft.record_session_argv_template).toContain("--citation-traced");
    expect(draft.record_session_argv_template).toContain("--dialogue-no-key-copy");
    expect(draft.record_session_command_template).toContain(
      "'No model provider configured; activation SPR-03.'",
    );
    expect(draft.observed_steps["7"]).toBe("pending operator 20-minute dogfood note");
  });

  it("shell-quotes apostrophes in observed operator text", () => {
    const draft = buildReadActivationEvidenceDraft({
      sessionId: "read-golden-path-e2e-abcdef0",
      date: "2026-07-03",
      buildSha: "abcdef0123456789",
      url: "http://localhost:4173/read/doc-1",
      operator: "operator",
      documentId: "doc-1",
      entryDoor: "library",
      visibleContentNote: "reader's heading rendered",
      selectedText: "reader's selected passage",
      dialogueNoKeyCopy: "Dialogue's provider boundary.",
      researchNoKeyCopy: "Research's provider boundary.",
      sourceDocumentId: "doc-source-42",
      chunkId: "chunk-7",
      resultUrl:
        "http://localhost:4173/read/doc-source-42?chunk=chunk-7&from=doc-1",
      returnContextNote: "Return reopened /read/doc-1?page=0",
    });

    expect(draft.record_session_command_template).toContain("'reader'\\''s heading rendered'");
    expect(draft.record_session_command_template).toContain(
      "'Dialogue'\\''s provider boundary.'",
    );
  });
});
