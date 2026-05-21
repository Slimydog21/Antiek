/**
 * Pure, side-effect-free helpers for the workspace panel system.
 *
 * Lives separately from the Zustand store so the math + array
 * manipulation is testable in isolation. The store imports from
 * here; nothing else in `src/workspace/` should re-implement these.
 */

import type { PanelDescriptor } from "./panel.types";

/** Distance from a floating panel's edge to the viewport edge that
 *  triggers a "snap to dock" preview. 24px feels deliberate without
 *  fighting the operator. */
export const SNAP_THRESHOLD_PX = 24;

/** Clamp a floating rect so it stays inside the viewport. Keeps the
 *  panel reachable on every monitor / window size. */
export function clampRectToViewport(
  rect: PanelDescriptor["rect"],
  viewport: { width: number; height: number },
): PanelDescriptor["rect"] {
  // Keep at least 80px of the panel visible on each side so the
  // operator can grab the handle even after an aggressive drag.
  const minVisible = 80;
  const x = Math.max(
    minVisible - rect.width,
    Math.min(viewport.width - minVisible, rect.x),
  );
  const y = Math.max(
    0,
    Math.min(viewport.height - minVisible, rect.y),
  );
  return { ...rect, x, y };
}

/** Detect whether a floating rect is close enough to a viewport edge
 *  to snap into a dock. Returns the dock side or `null`. */
export function snapToDock(
  rect: PanelDescriptor["rect"],
  viewport: { width: number; height: number },
): "left" | "right" | null {
  if (rect.x < SNAP_THRESHOLD_PX) return "left";
  if (rect.x + rect.width > viewport.width - SNAP_THRESHOLD_PX) return "right";
  return null;
}

/** Next z-index value. Pure: the store passes in the current zCounter. */
export function nextZ(zCounter: number): number {
  return zCounter + 1;
}

/**
 * Reorder one item inside an array (used by the dock drag-reorder).
 * Stable for items at the same target index. Out-of-bounds inputs
 * are treated as no-ops.
 */
export function reorderArray<T>(arr: T[], fromIndex: number, toIndex: number): T[] {
  if (fromIndex < 0 || fromIndex >= arr.length) return arr;
  if (toIndex < 0 || toIndex >= arr.length) return arr;
  if (fromIndex === toIndex) return arr;
  const copy = arr.slice();
  const [item] = copy.splice(fromIndex, 1);
  copy.splice(toIndex, 0, item);
  return copy;
}

/**
 * Choose an initial floating rect for a newly-opened panel. We cascade
 * each new floating panel ~22px right + down of the previous so they
 * don't stack exactly on top of each other.
 */
export function initialFloatingRect(z: number): PanelDescriptor["rect"] {
  return {
    x: 120 + ((z * 22) % 200),
    y: 120 + ((z * 22) % 200),
    width: 560,
    height: 420,
  };
}

/** Default docked size hint. The dock itself stretches; this is a
 *  per-panel preferred minimum. */
export function defaultDockedSize(): PanelDescriptor["size"] {
  return { width: 320, height: 0 };
}
