import { describe, it, expect } from "vitest";

import type { PaletteDragPayload } from "../../CreationStudio/BlockPalette";
import { paletteDragToPlaceBlock, parsePaletteDrag } from "./dragToOutline";

/**
 * Drag-preserves-provenance (SPR-03 M4 mechanical gate): dropping a
 * repository block into the outline creates an OutlineBlock referencing
 * the SAME node — never a copy — so trace-to-source stays intact.
 */

const insight: PaletteDragPayload = {
  from: "palette", block_kind: "insight", block_id: "node-abc", label: "an insight",
};

describe("paletteDragToPlaceBlock — provenance preserved", () => {
  it("carries the dragged node_id through as a graph_node reference", () => {
    const body = paletteDragToPlaceBlock(insight, {
      sectionId: "sec-1", blockIndex: 2, deliverableId: "dlv-1",
    });
    expect(body).toEqual({
      section_id: "sec-1",
      block_kind: "insight",
      provenance_kind: "graph_node",
      node_id: "node-abc", // SAME node — not duplicated
      block_index: 2,
      deliverable_id: "dlv-1",
    });
  });

  it("keeps graph_node provenance even for a non-node-kind drag", () => {
    const note: PaletteDragPayload = {
      from: "palette", block_kind: "operator_note", block_id: "node-9", label: "n",
    };
    const body = paletteDragToPlaceBlock(note, { sectionId: "s", blockIndex: 0 });
    // A repository block is a node reference regardless of surfaced kind;
    // it never loses provenance — lands as a node-backed claim.
    expect(body.provenance_kind).toBe("graph_node");
    expect(body.node_id).toBe("node-9");
    expect(body.block_kind).toBe("claim");
  });
});

describe("parsePaletteDrag", () => {
  it("parses a valid palette envelope", () => {
    expect(parsePaletteDrag(JSON.stringify(insight))).toEqual(insight);
  });
  it("rejects non-palette / malformed data", () => {
    expect(parsePaletteDrag("")).toBeNull();
    expect(parsePaletteDrag("not json")).toBeNull();
    expect(parsePaletteDrag(JSON.stringify({ from: "section", block_id: "x" }))).toBeNull();
    expect(parsePaletteDrag(JSON.stringify({ from: "palette" }))).toBeNull();
  });
});
