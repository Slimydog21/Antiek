import { useCallback } from "react";

import { placeBlock } from "../writeApi";
import { paletteDragToPlaceBlock, parsePaletteDrag } from "./dragToOutline";

/**
 * Outline drop-target hook (specs/write/ SPR-03 M3+M4).
 *
 * Attach the returned handlers to the region of the outline that accepts
 * dragged repository blocks. On drop, the palette envelope is mapped to a
 * place-block request that **preserves provenance** (same node_id,
 * graph_node — the tested invariant in dragToOutline.ts) and committed via
 * ``POST /write/blocks``. ``onPlaced`` fires with the new
 * outline_block_id so the host can refresh.
 *
 * Drop position respects the outline order via ``blockIndexAt`` (the host
 * supplies the index for the drop point).
 */
export interface UseOutlineDropOptions {
  sectionId: string;
  deliverableId?: string;
  /** Resolve the block_index for the drop point (default: append). */
  blockIndexAt?: (e: React.DragEvent) => number;
  onPlaced?: (outlineBlockId: string) => void | Promise<void>;
  onError?: (err: unknown) => void;
}

export interface OutlineDropHandlers {
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
}

export function useOutlineDrop(opts: UseOutlineDropOptions): OutlineDropHandlers {
  const { sectionId, deliverableId, blockIndexAt, onPlaced, onError } = opts;

  const onDragOver = useCallback((e: React.DragEvent) => {
    // Allow the drop only for our payload (keeps native text drops out).
    if (e.dataTransfer.types.includes("application/x-antiek-block")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      const payload = parsePaletteDrag(e.dataTransfer);
      if (!payload) return; // not a repository block — ignore
      e.preventDefault();
      const blockIndex = blockIndexAt ? blockIndexAt(e) : 0;
      const body = paletteDragToPlaceBlock(payload, {
        sectionId, blockIndex, deliverableId,
      });
      placeBlock(body).then(
        (obid) => {
          try {
            void Promise.resolve(onPlaced?.(obid)).catch(() => undefined);
          } catch {
            // Placement committed; a consumer refresh cannot reclassify it.
          }
        },
        (err) => onError?.(err),
      );
    },
    [sectionId, deliverableId, blockIndexAt, onPlaced, onError],
  );

  return { onDragOver, onDrop };
}
