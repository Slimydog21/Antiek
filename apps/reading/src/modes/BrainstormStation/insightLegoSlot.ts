/**
 * Surface E Lego insight slotting — pure helpers (master-spec §4.5).
 *
 * Reuses Write/CreationStudio drag contract (`PaletteDragPayload` /
 * `DRAG_MIME` / `parsePaletteDrag`) so insights are one object across
 * outline assembly and thought-partner focus. Dropped blocks become
 * `@insight` items for `POST /compose-context` (CK-4 / §9.0), then
 * merge into ThoughtPartner `system_context` — no second drag system,
 * no invented product surface.
 *
 * Cite: docs/master-product-spec.md §4.5 Lego-block slotting;
 * docs/decisions/write-artifact-bridge.md; dragToOutline.ts.
 */
import type { ContextItem } from "../../lib/api";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { parsePaletteDrag } from "../Write/Repository/dragToOutline";

export { parsePaletteDrag };

/** Deduped append — same node can only occupy one focus slot. */
export function slotInsight(
  current: PaletteDragPayload[],
  incoming: PaletteDragPayload,
  max = 12,
): PaletteDragPayload[] {
  if (!incoming.block_id) return current;
  if (current.some((s) => s.block_id === incoming.block_id)) return current;
  if (current.length >= max) return current;
  return [...current, incoming];
}

export function unslotInsight(
  current: PaletteDragPayload[],
  blockId: string,
): PaletteDragPayload[] {
  return current.filter((s) => s.block_id !== blockId);
}

/** Map slotted Lego blocks → compose-context @insight items. */
export function slottedToContextItems(
  slotted: PaletteDragPayload[],
): ContextItem[] {
  return slotted
    .filter((s) => typeof s.block_id === "string" && s.block_id.length > 0)
    .map((s) => ({ kind: "insight" as const, id: s.block_id }));
}

/**
 * Merge composed insight context with any prior picker / reading focus.
 * Insights first (operator explicitly slotted them into focus).
 */
export function mergeSlottedSystemContext(
  insightContext: string | null | undefined,
  baseContext: string | null | undefined,
): string {
  const a = (insightContext ?? "").trim();
  const b = (baseContext ?? "").trim();
  if (a && b) return `${a}\n\n${b}`;
  return a || b;
}
