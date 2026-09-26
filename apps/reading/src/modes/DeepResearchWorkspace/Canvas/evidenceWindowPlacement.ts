import type { WindowRect } from "../../../workspace/windowsStore";

export interface SourceAnchorRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

export interface PlacementViewport {
  width: number;
  height: number;
}

export interface EvidenceWindowSize {
  width: number;
  height: number;
}

export const EVIDENCE_WINDOW_GUTTER_PX = 16;

/**
 * Choose a whole-window placement beside the source control. Right and left
 * preserve the reading line first; below and above are honest fallbacks. When
 * no candidate fits entirely inside the host, return undefined so the existing
 * window cascade owns placement instead of fabricating non-overlap.
 */
export function chooseEvidenceWindowRect(
  anchor: SourceAnchorRect,
  viewport: PlacementViewport,
  size: EvidenceWindowSize,
  gutter = EVIDENCE_WINDOW_GUTTER_PX,
): WindowRect | undefined {
  if (
    viewport.width <= 0 ||
    viewport.height <= 0 ||
    size.width <= 0 ||
    size.height <= 0 ||
    size.width > viewport.width ||
    size.height > viewport.height
  ) {
    return undefined;
  }

  const alignedY = Math.max(0, Math.min(anchor.top, viewport.height - size.height));
  const alignedX = Math.max(0, Math.min(anchor.left, viewport.width - size.width));
  const candidates: WindowRect[] = [
    { x: anchor.right + gutter, y: alignedY, ...size },
    { x: anchor.left - gutter - size.width, y: alignedY, ...size },
    { x: alignedX, y: anchor.bottom + gutter, ...size },
    { x: alignedX, y: anchor.top - gutter - size.height, ...size },
  ];

  return candidates.find(
    ({ x, y, width, height }) =>
      x >= 0 && y >= 0 && x + width <= viewport.width && y + height <= viewport.height,
  );
}
