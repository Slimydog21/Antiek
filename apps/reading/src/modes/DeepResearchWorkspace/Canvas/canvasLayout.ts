/**
 * Pure, side-effect-free layout helpers for the DRW block-canvas (Living
 * Roadmap SPR-03). Lives separately from the React components so the math —
 * event replay, deterministic auto-layout, drag clamping — is testable in
 * isolation, mirroring `src/workspace/panelLayoutLogic.ts`.
 *
 * NOTHING here imports React, the API client, or reading-physics: it is pure
 * geometry over plain data. The canvas is a FREE 2D coordinate space, NOT the
 * reading-physics in-document layout-map; this module never touches that map.
 */

import type { BlockPositionPayload, Event } from "../../../generated/types";

/** A block's resolved position on the canvas. */
export interface BlockPosition {
  x: number;
  y: number;
  /** M4 theme grouping — the region this block belongs to (null = ungrouped). */
  regionId: string | null;
  regionLabel: string | null;
  /** True when this came from a persisted drag event; false when it is a
   *  deterministic auto-layout fallback (a node the operator never dragged). */
  persisted: boolean;
}

export const BLOCK_WIDTH = 240;
export const BLOCK_HEIGHT = 96;

/** Keep at least this many px of a block reachable on every edge after a
 *  drag — the same 80px reachability rule `clampRectToViewport` uses for
 *  workspace panels (src/workspace/panelLayoutLogic.ts:23). */
const MIN_VISIBLE = 80;

/**
 * Clamp a block's top-left so it can't be dragged completely off the canvas
 * viewport. Keeps ≥ MIN_VISIBLE px reachable on each side. Mirrors
 * `clampRectToViewport` but for fixed-size canvas blocks (we don't carry a
 * per-block width/height through the event, so the constants above stand in).
 */
export function clampBlockToViewport(
  pos: { x: number; y: number },
  viewport: { width: number; height: number },
): { x: number; y: number } {
  const x = Math.max(
    MIN_VISIBLE - BLOCK_WIDTH,
    Math.min(viewport.width - MIN_VISIBLE, pos.x),
  );
  const y = Math.max(0, Math.min(viewport.height - MIN_VISIBLE, pos.y));
  return { x, y };
}

/**
 * Deterministic auto-layout for a node with no persisted position. A simple
 * column-major grid keyed by the node's index in a stable ordering — NEVER
 * (0,0) for everything (the rigor #3 "pile-up" edge case). Same inputs →
 * same output, so an un-dragged graph lays out identically every reload.
 */
export function autoLayoutPosition(index: number): { x: number; y: number } {
  const COLS = 4;
  const GAP_X = 280;
  const GAP_Y = 150;
  const MARGIN = 40;
  const col = index % COLS;
  const row = Math.floor(index / COLS);
  return {
    x: MARGIN + col * GAP_X,
    y: MARGIN + row * GAP_Y,
  };
}

/** A type guard narrowing an Event to one carrying a BlockPositionPayload. */
export function isBlockPositionEvent(
  e: Event,
): e is Event & { payload: BlockPositionPayload } {
  return e.payload.action_type === "block.positioned";
}

/**
 * Replay the persisted `block.positioned` events into a node_id → position
 * map. Latest event per node_id wins (last-writer-wins is correct here:
 * positions are not provenance and have no merge semantics — the operator's
 * most recent drag is authoritative). Events are ordered by `emitted_at`
 * ascending; ties broken by array order (the event log is already
 * append-ordered).
 *
 * This is the SINGLE source of truth for position — there is no client
 * side-store. A node absent from this map gets an auto-layout fallback at
 * resolve time.
 */
export function replayPositions(events: Event[]): Map<string, BlockPosition> {
  const ordered = [...events]
    .filter(isBlockPositionEvent)
    .sort((a, b) => {
      const ta = a.emitted_at ?? "";
      const tb = b.emitted_at ?? "";
      // Stable: equal timestamps keep input (append) order.
      return ta < tb ? -1 : ta > tb ? 1 : 0;
    });
  const out = new Map<string, BlockPosition>();
  for (const e of ordered) {
    const p = e.payload;
    out.set(p.node_id, {
      x: p.x,
      y: p.y,
      regionId: p.region_id ?? null,
      regionLabel: p.region_label ?? null,
      persisted: true,
    });
  }
  return out;
}

/**
 * Resolve a final position for every node: persisted event if present, else
 * deterministic auto-layout (so a node never piles up at (0,0)). `nodeIds`
 * must be in a stable order so auto-layout is reproducible across reloads.
 */
export function resolvePositions(
  nodeIds: string[],
  persisted: Map<string, BlockPosition>,
): Map<string, BlockPosition> {
  const out = new Map<string, BlockPosition>();
  let autoIndex = 0;
  for (const id of nodeIds) {
    const saved = persisted.get(id);
    if (saved) {
      out.set(id, saved);
    } else {
      const auto = autoLayoutPosition(autoIndex);
      autoIndex += 1;
      out.set(id, {
        x: auto.x,
        y: auto.y,
        regionId: null,
        regionLabel: null,
        persisted: false,
      });
    }
  }
  return out;
}

/** The bounding box (min/max corners) of a set of block top-left positions,
 *  inflated to cover each block's full extent. Used to draw an M4 theme
 *  region rectangle around its members. Returns null for an empty set. */
export function regionBounds(
  positions: Array<{ x: number; y: number }>,
): { x: number; y: number; width: number; height: number } | null {
  if (positions.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of positions) {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x + BLOCK_WIDTH);
    maxY = Math.max(maxY, p.y + BLOCK_HEIGHT);
  }
  const PAD = 16;
  return {
    x: minX - PAD,
    y: minY - PAD,
    width: maxX - minX + PAD * 2,
    height: maxY - minY + PAD * 2,
  };
}
