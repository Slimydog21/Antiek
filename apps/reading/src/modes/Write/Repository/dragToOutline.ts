/**
 * Drag-into-outline mapping (specs/write/ SPR-03 M3+M4).
 *
 * The operator's outlining workflow is "heavily reliant on the research
 * folders to drag insights into the outline." When a repository block is
 * dropped into the outline it must create an **OutlineBlock referencing
 * the same graph node** — never a copy — so trace-to-source (SPR-07) stays
 * intact. That guarantee (the SPR-03 M4 mechanical gate, "drag preserves
 * provenance") lives in this pure mapping, so it is unit-testable without
 * a browser.
 *
 * The drag payload is the existing palette envelope (CreationStudio's
 * ``PaletteDragPayload``); the output is the ``POST /write/blocks`` body
 * (the SPR-01 place_block REST contract). provenance_kind is always
 * ``graph_node`` with the dragged ``node_id`` carried through — a
 * repository block is a node reference, so dropping it can never mint
 * orphan prose.
 */

import type { PaletteDragPayload } from "../../CreationStudio/BlockPalette";
import { DRAG_MIME } from "../../CreationStudio/BlockPalette";

/** The /write/blocks request body (SPR-01 place_block over REST). */
export interface PlaceBlockBody {
  section_id: string;
  block_kind: "insight" | "open_question" | "claim";
  provenance_kind: "graph_node";
  node_id: string;
  block_index: number;
  deliverable_id?: string;
}

// Graph-node-backed block kinds (the kinds that pair with graph_node
// provenance — see substrate/write/outline_block._COHERENT_PAIRS). A
// repository block that surfaced under any other kind is a node reference
// regardless, so it lands as a "claim" (a node-backed kind) rather than
// losing its provenance.
const _NODE_KINDS = new Set(["insight", "open_question", "claim"]);

function _nodeKind(kind: string): "insight" | "open_question" | "claim" {
  return (_NODE_KINDS.has(kind) ? kind : "claim") as
    | "insight"
    | "open_question"
    | "claim";
}

/** Parse a palette drag payload off a DataTransfer (or raw string).
 * Returns null when the data is absent/malformed (a non-palette drop). */
export function parsePaletteDrag(
  source: DataTransfer | string | null,
): PaletteDragPayload | null {
  const raw = typeof source === "string" ? source : source?.getData(DRAG_MIME) ?? "";
  if (!raw) return null;
  try {
    const obj = JSON.parse(raw) as Partial<PaletteDragPayload>;
    if (obj.from !== "palette" || typeof obj.block_id !== "string") return null;
    return obj as PaletteDragPayload;
  } catch {
    return null;
  }
}

/**
 * Map a dropped repository block to the place-block request — preserving
 * provenance (same node_id, graph_node). This is the moat: the dropped
 * block resolves the same node → document → chunks the source did.
 */
export function paletteDragToPlaceBlock(
  payload: PaletteDragPayload,
  opts: { sectionId: string; blockIndex: number; deliverableId?: string },
): PlaceBlockBody {
  return {
    section_id: opts.sectionId,
    block_kind: _nodeKind(payload.block_kind),
    provenance_kind: "graph_node",
    node_id: payload.block_id, // the SAME node — not a copy
    block_index: opts.blockIndex,
    deliverable_id: opts.deliverableId,
  };
}
