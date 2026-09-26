/**
 * anchorRanges + pinBody unit proofs (anchor-first SPR-02).
 *
 * The pure geometry (body-anchored ranges → page-relative marks) and the
 * §9.0 pin boundary (a withheld selection posts ids/numbers only, never a
 * quote field).
 */
import { describe, expect, it } from "vitest";

import type { AnchorMapChunk, BookAnchor } from "../../lib/api";
import type { PageWindow } from "./paginate";
import {
  anchorBodyRange,
  chunkIdAtOffset,
  normalizeNodeText,
  orphanedForList,
  rangesForPage,
} from "./anchorRanges";
import { buildPinBody } from "./pinBody";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";

const BODY = "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.";
const CHUNK: AnchorMapChunk = {
  chunk_id: "c-1",
  section_path: "Page 1",
  body_start: 10,
  body_end: 32,
  node_text_sha256: "h".repeat(64),
};

function anchor(over: Partial<BookAnchor> = {}): BookAnchor {
  return {
    anchor_id: "a-1",
    document_id: "doc-1",
    anchor: {
      normalization: "unicode-nfc-v1",
      node_id: "c-1",
      node_text_sha256: "h".repeat(64),
      start_scalar: 0,
      end_scalar: 7,
      quote: "The ope",
      prefix: "",
      suffix: "ning of the book.",
    },
    servable_at_pin: true,
    selection_text_sha256: "s".repeat(64),
    page_index_hint: 0,
    source: "pin",
    status: "active",
    exact_valid: true,
    investigation_id: null,
    created_at: "2026-09-24T10:00:00Z",
    updated_at: "2026-09-24T10:00:00Z",
    ...over,
  };
}

const PAGE: PageWindow = {
  pageIndex: 0,
  pageNumber: 1,
  text: "The opening of the book.",
  bodyStart: 10,
};

describe("normalizeNodeText (the unicode-nfc-v1 client mirror)", () => {
  it("collapses CRLF and CR to LF and applies NFC", () => {
    expect(normalizeNodeText("a\r\nb\rc")).toBe("a\nb\nc");
    expect(normalizeNodeText("e\u0301")).toBe("é");
  });
});

describe("anchorBodyRange", () => {
  it("maps a chunk-relative passage to body offsets via the anchor-map", () => {
    const range = anchorBodyRange(anchor(), new Map([["c-1", CHUNK]]));
    expect(range).toEqual({ start: 10, end: 17 });
  });

  it("returns null when the chunk is not in the manifest (an orphaned anchor's chunk)", () => {
    expect(anchorBodyRange(anchor(), new Map())).toBeNull();
  });
});

describe("rangesForPage", () => {
  it("paints the active anchor at the correct passage on the correct page", () => {
    const ranges = rangesForPage(PAGE, [anchor()], new Map([["c-1", CHUNK]]));
    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toMatchObject({
      anchorId: "a-1",
      start: 0,
      end: 7,
      treatment: "active",
    });
    expect(PAGE.text.slice(0, 7)).toBe("The ope");
  });

  it("a drifted anchor paints the drifted treatment; an orphaned anchor never paints", () => {
    const drifted = anchor({ anchor_id: "a-2", status: "drifted" });
    const orphaned = anchor({ anchor_id: "a-3", status: "orphaned" });
    const ranges = rangesForPage(PAGE, [drifted, orphaned], new Map([["c-1", CHUNK]]));
    expect(ranges).toHaveLength(1);
    expect(ranges[0].anchorId).toBe("a-2");
    expect(ranges[0].treatment).toBe("drifted");
    expect(ranges[0].title).toContain("Moved");
  });

  it("clips a range that spans past the page boundary and skips other pages' ranges", () => {
    const spanning = anchor({
      anchor: { ...anchor().anchor, start_scalar: 15, end_scalar: 50 },
    });
    const ranges = rangesForPage(PAGE, [spanning], new Map([["c-1", CHUNK]]));
    expect(ranges).toHaveLength(1);
    expect(ranges[0].start).toBe(15);
    expect(ranges[0].end).toBe(PAGE.text.length);
  });
});

describe("orphanedForList", () => {
  it("lists only orphaned anchors, oldest first", () => {
    const list = orphanedForList([
      anchor({ anchor_id: "b", status: "orphaned", created_at: "2026-09-24T11:00:00Z" }),
      anchor({ anchor_id: "a", status: "active" }),
      anchor({ anchor_id: "c", status: "orphaned", created_at: "2026-09-24T09:00:00Z" }),
    ]);
    expect(list.map((a) => a.anchor_id)).toEqual(["c", "b"]);
  });
});

describe("chunkIdAtOffset (the HONEST GAP closure)", () => {
  it("resolves the chunk containing a body offset; null between chunks", () => {
    expect(chunkIdAtOffset(12, [CHUNK])).toBe("c-1");
    expect(chunkIdAtOffset(33, [CHUNK])).toBeNull();
  });
});

// ── The §9.0 pin boundary (buildPinBody) ─────────────────────────────────

function sel(servable: boolean | undefined): FloatMenuSelection {
  return {
    text: "The ope",
    rect: { top: 1, left: 1, width: 10, height: 10 },
    provenance: { documentId: "doc-1", chunkId: "c-1", servable },
  };
}

const LOC = { chunkId: "c-1", start: 0, end: 7, bodyOffset: 10 };

describe("buildPinBody", () => {
  it("a servable selection posts the quote with host-located context", () => {
    const body = buildPinBody("pin", sel(true), LOC, BODY, 0);
    expect(body).toMatchObject({ quote: "The ope", source: "pin", page_index_hint: 0 });
    expect(body?.quote).toBe("The ope");
    expect("node_id" in (body ?? {})).toBe(false);
  });

  it("a WITHHELD selection posts ids/numbers only — NO quote field anywhere", () => {
    const body = buildPinBody("floatmenu_note", sel(false), LOC, BODY, 0);
    expect(body).toBeTruthy();
    expect(body).not.toHaveProperty("quote");
    expect(body).toMatchObject({
      node_id: "c-1",
      start_scalar: 0,
      end_scalar: 7,
      source: "floatmenu_note",
    });
    expect(JSON.stringify(body)).not.toContain("The ope");
  });

  it("no unique location pins nothing, whatever the servability", () => {
    expect(buildPinBody("pin", sel(true), null, BODY, 0)).not.toBeNull(); // quote path still posts (server resolves)
    expect(buildPinBody("pin", sel(false), null, BODY, 0)).toBeNull(); // metadata-only has no location → nothing
  });

  it("an unresolved servable provenance (undefined) still posts the quote", () => {
    const body = buildPinBody("pin", sel(undefined), LOC, BODY, 0);
    expect(body).toHaveProperty("quote", "The ope");
  });
});
