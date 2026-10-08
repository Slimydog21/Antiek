/** composerChips.test.ts — SPR-07 M2 (pattern 11): chips serialize deterministically; sources come from the tree when it is ready. */
import { describe, expect, it } from "vitest";

import { EMPTY_TREE } from "../contracts/treeStore";
import type { ContextTree } from "../contracts/tree";
import { backspaceRemovesLastChip, serializeDraft, sourceCandidates, type ComposerChip } from "./composerChips";

const chips: ComposerChip[] = [
  { kind: "agent", id: "x:1", label: "A" },
  { kind: "source", id: "doc-1", label: "S" },
];

describe("composerChips", () => {
  it("serializes `@A #S body`", () => {
    expect(serializeDraft(chips, "what next?")).toBe("@A #S what next?");
    expect(serializeDraft([], "plain")).toBe("plain");
    expect(serializeDraft(chips, "")).toBe("@A #S");
  });

  it("Backspace on an empty body removes the last chip; on a body it removes nothing", () => {
    expect(backspaceRemovesLastChip(chips, "")).toEqual({ chips: [chips[0]], removed: chips[1] });
    expect(backspaceRemovesLastChip(chips, "x")).toEqual({ chips, removed: null });
    expect(backspaceRemovesLastChip([], "")).toEqual({ chips: [], removed: null });
  });

  it("offers the selected project's members when the tree is ready, else the open left reader tabs", () => {
    const ready: ContextTree = {
      ...EMPTY_TREE,
      status: "ready",
      roots: [{
        id: "proj-1", kind: "project", title: "P", parentId: null, children: [], agents: [], archived: false,
        provenance: "backend", source: { kind: "default" },
        members: [
          { member_kind: "document", member_id: "doc-a", added_at: "2026-10-07T00:00:00Z" },
          { member_kind: "investigation", member_id: "inv-1", added_at: "2026-10-07T00:00:00Z" },
        ],
      }],
    };
    const tabs = [{ id: "doc-z", title: "Open Z" }];
    expect(sourceCandidates(ready, { projectId: "proj-1" }, tabs)).toEqual([
      { id: "doc-a", label: "doc-a" },
      { id: "inv-1", label: "inv-1" },
    ]);
    expect(sourceCandidates(EMPTY_TREE, { projectId: "proj-1" }, tabs)).toEqual([{ id: "doc-z", label: "Open Z" }]);
    // A ready tree whose members were never fetched (absent ≠ none) falls back too.
    const unfetched: ContextTree = { ...ready, roots: [{ ...ready.roots[0], members: undefined }] };
    expect(sourceCandidates(unfetched, { projectId: "proj-1" }, tabs)).toEqual([{ id: "doc-z", label: "Open Z" }]);
  });
});
