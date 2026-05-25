import { describe, it, expect } from "vitest";

import type { EditorBlock } from "./locator";
import { diffBlocks, toEditCapturedPayload } from "./editCapture";

/**
 * Granular edit capture (SPR-04 M5): edits emit at the right granularity,
 * and undo/redo does NOT count reverted edits as positive signal.
 */

function prose(blockId: string, text: string): EditorBlock {
  return { blockId, text, kind: "prose" };
}

describe("diffBlocks", () => {
  it("detects a replace (text changed in place)", () => {
    const edits = diffBlocks("sec-1", [prose("a", "old")], [prose("a", "new")]);
    expect(edits).toHaveLength(1);
    expect(edits[0].kind).toBe("replace");
    expect(edits[0].beforeText).toBe("old");
    expect(edits[0].afterText).toBe("new");
    expect(edits[0].reverted).toBe(false);
  });

  it("detects an insert", () => {
    const edits = diffBlocks("sec-1", [prose("a", "x")], [prose("a", "x"), prose("b", "y")]);
    expect(edits).toHaveLength(1);
    expect(edits[0].kind).toBe("insert");
    expect(edits[0].locator.blockId).toBe("b");
    expect(edits[0].afterText).toBe("y");
  });

  it("detects a delete", () => {
    const edits = diffBlocks("sec-1", [prose("a", "x"), prose("b", "y")], [prose("a", "x")]);
    expect(edits).toHaveLength(1);
    expect(edits[0].kind).toBe("delete");
    expect(edits[0].locator.blockId).toBe("b");
    expect(edits[0].beforeText).toBe("y");
  });

  it("detects a reorder when the id set is unchanged but order differs", () => {
    const edits = diffBlocks(
      "sec-1",
      [prose("a", "x"), prose("b", "y")],
      [prose("b", "y"), prose("a", "x")],
    );
    expect(edits).toHaveLength(1);
    expect(edits[0].kind).toBe("reorder");
  });

  it("emits nothing when nothing changed", () => {
    expect(diffBlocks("sec-1", [prose("a", "x")], [prose("a", "x")])).toEqual([]);
  });
});

describe("undo/redo coordination — reverts are not signal", () => {
  it("flags undo-produced edits as reverted", () => {
    // Forward edit: 'old' → 'new'.
    const forward = diffBlocks("sec-1", [prose("a", "old")], [prose("a", "new")]);
    expect(forward[0].reverted).toBe(false);

    // Undo reverses it: 'new' → 'old', captured as an undo transaction.
    const undo = diffBlocks(
      "sec-1", [prose("a", "new")], [prose("a", "old")], { isUndo: true },
    );
    expect(undo[0].reverted).toBe(true); // excluded from training signal
  });
});

describe("toEditCapturedPayload", () => {
  it("maps to the backend edit.captured payload shape", () => {
    const [edit] = diffBlocks("sec-1", [prose("a", "old")], [prose("a", "new")]);
    const payload = toEditCapturedPayload("dlv-1", edit, "session-1");
    expect(payload).toEqual({
      action_type: "edit.captured",
      deliverable_id: "dlv-1",
      section_id: "sec-1",
      outline_block_id: null,
      granularity: "block",
      edit_kind: "replace",
      paragraph_index: 0,
      sentence_index: null,
      before_text: "old",
      after_text: "new",
      reverted: false,
      session_id: "session-1",
    });
  });
});
