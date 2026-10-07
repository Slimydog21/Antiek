/**
 * anchor.test.ts — SPR-06 M1/M4: DocumentAnchor guards, the producers
 * (pin / locate / writer block) and the wire projection (toBranchAnchor).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import type { BookAnchor } from "../../lib/api";
import { emptyTabTree, fromSnapshot, spawnChild, toSnapshot, type BranchAnchor } from "../tabTree";
import {
  anchorFromLocate,
  anchorFromPin,
  anchorFromWriterBlock,
  anchorKey,
  isDocumentAnchor,
  toBranchAnchor,
  type BookDocumentAnchor,
  type DeliverableDocumentAnchor,
  type DocumentAnchor,
} from "./anchor";

const SHA_A = "a".repeat(64);
const SHA_C = "c".repeat(64);

const pinned: BookAnchor = {
  anchor_id: "ahl-1",
  document_id: "doc-1",
  anchor: {
    normalization: "unicode-nfc-v1",
    node_id: "chunk-1",
    node_text_sha256: SHA_A,
    start_scalar: 3,
    end_scalar: 9,
    quote: "passage",
    prefix: "pre",
    suffix: "suf",
  },
  servable_at_pin: true,
  selection_text_sha256: "b".repeat(64),
  page_index_hint: 2,
  source: "pin",
  status: "active",
  exact_valid: true,
  investigation_id: null,
  created_at: "2026-10-07T00:00:00Z",
  updated_at: "2026-10-07T00:00:00Z",
};

function textAnchor(over: Partial<BookDocumentAnchor> = {}): BookDocumentAnchor {
  return {
    space: "book",
    documentId: "doc-1",
    version: { kind: "node_text_sha256", nodeId: "chunk-1", sha256: SHA_A },
    kind: "text",
    range: { kind: "text", nodeId: "chunk-1", start: 0, end: 5, unit: "utf16", basis: "chunk" },
    quoteHint: null,
    ...over,
  };
}

async function digest(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, "0")).join("");
}

describe("A1 isDocumentAnchor", () => {
  it("accepts a sound text anchor", () => {
    expect(isDocumentAnchor(textAnchor())).toBe(true);
  });
  it("rejects a missing version", () => {
    const { version: _v, ...rest } = textAnchor();
    expect(isDocumentAnchor(rest)).toBe(false);
  });
  it("rejects node_text_sha256 with an empty sha", () => {
    expect(isDocumentAnchor(textAnchor({ version: { kind: "node_text_sha256", nodeId: "chunk-1", sha256: "" } }))).toBe(false);
  });
  it("rejects kind !== range.kind", () => {
    expect(isDocumentAnchor({ ...textAnchor(), kind: "page" })).toBe(false);
  });
  it("rejects an empty quoteHint.quote", () => {
    expect(isDocumentAnchor(textAnchor({ quoteHint: { quote: "", prefix: "", suffix: "" } }))).toBe(false);
  });
  it("rejects book space with kind block and deliverable space with kind text", () => {
    const block = { kind: "block", sectionId: "s1", outlineBlockId: null, paragraphIndex: 0 } as const;
    expect(isDocumentAnchor({ ...textAnchor(), kind: "block", range: block })).toBe(false);
    expect(isDocumentAnchor({ ...textAnchor(), space: "deliverable", deliverableId: "d1" })).toBe(false);
  });
});

describe("A2 anchorFromLocate", () => {
  it("is a chunk-relative UTF-16 text anchor whose wire form is id + page only", () => {
    const a = anchorFromLocate("doc-1", { chunkId: "chunk-1", start: 0, end: 5 }, "b".repeat(64), null, 3);
    expect(a.range).toEqual({ kind: "text", nodeId: "chunk-1", start: 0, end: 5, unit: "utf16", basis: "chunk" });
    expect(a.version).toEqual({ kind: "node_text_sha256", nodeId: "chunk-1", sha256: "b".repeat(64) });
    expect(isDocumentAnchor(a)).toBe(true);
    expect(toBranchAnchor(a)).toStrictEqual({ document_id: "doc-1", page_index: 3 });
  });
  it("without a chunk digest the version is an explicit metadata-only absence", () => {
    const a = anchorFromLocate("doc-1", { chunkId: "chunk-1", start: 0, end: 5 }, null, null, null);
    expect(a.version).toEqual({ kind: "unversioned", reason: "metadata_only_anchor" });
    expect(toBranchAnchor(a)).toStrictEqual({ document_id: "doc-1" });
  });
});

describe("A3 anchorFromPin", () => {
  it("carries the quote hint onto the wire, never a source_locator", () => {
    const a = anchorFromPin(pinned);
    expect(a.range).toEqual({ kind: "text", nodeId: "chunk-1", start: 3, end: 9, unit: "scalar", basis: "chunk" });
    expect(a.anchorId).toBe("ahl-1");
    expect(Object.hasOwn(a, "investigationId")).toBe(false);
    expect(a.status).toBe("active");
    expect(toBranchAnchor(a)).toStrictEqual({ document_id: "doc-1", quote: "passage", prefix: "pre", suffix: "suf", page_index: 2 });
  });
  it("a metadata-only pin has no quote keys; a null page hint has no page_index", () => {
    const a = anchorFromPin({ ...pinned, anchor: { ...pinned.anchor, quote: null, prefix: null, suffix: null }, investigation_id: "inv-1" });
    expect(a.quoteHint).toBeNull();
    expect(a.investigationId).toBe("inv-1");
    expect(toBranchAnchor(a)).toStrictEqual({ document_id: "doc-1", page_index: 2 });
    const b = anchorFromPin({ ...pinned, page_index_hint: null });
    expect(Object.hasOwn(toBranchAnchor(b), "page_index")).toBe(false);
  });
});

describe("A4 source_locator", () => {
  it("is emitted only for document-global scalar offsets with a selection digest", () => {
    const a = textAnchor({ range: { kind: "text", nodeId: "chunk-1", start: 10, end: 20, unit: "scalar", basis: "document", selectionSha256: SHA_C } });
    const wire = toBranchAnchor(a);
    expect(wire.source_locator).toEqual({ start: 10, end: 20, text_sha256: SHA_C });
    expect(wire.source_locator!.text_sha256).not.toBe((a.version as { sha256: string }).sha256);
    const bad = textAnchor({ range: { kind: "text", nodeId: "chunk-1", start: 10, end: 20, unit: "scalar", basis: "document", selectionSha256: "not-hex" } });
    expect(Object.hasOwn(toBranchAnchor(bad), "source_locator")).toBe(false);
    const chunk = textAnchor({ range: { kind: "text", nodeId: "chunk-1", start: 10, end: 20, unit: "scalar", basis: "chunk", selectionSha256: SHA_C } });
    expect(Object.hasOwn(toBranchAnchor(chunk), "source_locator")).toBe(false);
  });
});

describe("A5 anchorFromWriterBlock", () => {
  it("digests the prose itself and never reads a store", async () => {
    const a = await anchorFromWriterBlock({ deliverableId: "d1", sectionId: "s1", outlineBlockId: "ob1", paragraphIndex: 2, proseText: "hello" });
    expect(a.space).toBe("deliverable");
    expect(a.kind).toBe("block");
    expect(a.version).toEqual({ kind: "prose_text_sha256", sha256: await digest("hello") });
    expect(isDocumentAnchor(a)).toBe(true);
    const b = await anchorFromWriterBlock({ deliverableId: "d1", sectionId: "s1", outlineBlockId: null, paragraphIndex: null, proseText: null });
    expect(b.version).toEqual({ kind: "unversioned", reason: "writer_prose_block_unpersisted" });
    const here = typeof __dirname === "string" ? __dirname : resolve(process.cwd(), "src/workspace/contracts");
    const src = readFileSync(resolve(here, "anchor.ts"), "utf8");
    expect(src).not.toMatch(/zustand/);
  });
});

describe("A6 anchorKey", () => {
  it("separates UTF-16 from scalar offsets and stays prefix-recoverable to the dedupe tuple", () => {
    const astral = "x\u{1F600}y"; // 3 scalars, 4 UTF-16 units
    const utf16 = textAnchor({ range: { kind: "text", nodeId: "chunk-1", start: 0, end: astral.length, unit: "utf16", basis: "chunk" } });
    const scalar = textAnchor({ range: { kind: "text", nodeId: "chunk-1", start: 0, end: [...astral].length, unit: "scalar", basis: "chunk" } });
    expect(anchorKey(utf16)).not.toBe(anchorKey(scalar));
    const parts = anchorKey(scalar).split("|");
    expect(parts.slice(0, 3)).toEqual(["book", "doc-1", "text"]);
    expect(parts.slice(3, 6)).toEqual(["chunk-1", "0", "3"]);
    const block: DeliverableDocumentAnchor = {
      space: "deliverable", deliverableId: "d1", version: { kind: "unversioned", reason: "writer_prose_block_unpersisted" },
      kind: "block", range: { kind: "block", sectionId: "s1", outlineBlockId: null, paragraphIndex: null }, quoteHint: null,
    };
    expect(anchorKey(block)).toBe("deliverable|d1|block|s1||");
    const page: DocumentAnchor = { ...textAnchor(), kind: "page", range: { kind: "page", pageIndex: 4 } };
    expect(anchorKey(page)).toBe("book|doc-1|page|4");
  });
});

describe("A7 wire compatibility", () => {
  it("toBranchAnchor satisfies BranchAnchor and round-trips through fromSnapshot", () => {
    const wire: BranchAnchor = toBranchAnchor(anchorFromPin(pinned));
    const spawned = spawnChild(emptyTabTree("reading"), null, {
      tab_id: "t1", kind: "reader", ref: "doc-1", mothership: "reading",
      origin: { document_id: "doc-1", kind: "agent", anchor: wire },
      opened_by: { thread_id: "inv-1", agent_kind: "research" },
    });
    expect(spawned.ok).toBe(true);
    if (!spawned.ok) return;
    const back = fromSnapshot(toSnapshot(spawned.tree));
    expect(back.ok).toBe(true);
    if (!back.ok) return;
    expect(back.tree.nodes.t1.branch_origin?.anchor).toEqual(wire);
  });
});
