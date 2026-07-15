/**
 * Flipbook-feel interactive scene regions (HTML path).
 *
 * Pure viewport-adaptive hotspots over the procedural mountainscape.
 * These are NOT a generative pixel stream — they reshape with the window
 * and can receive hover/click handlers when a chrome layer enables
 * pointer-events on a hotspot overlay.
 *
 * LOAD-BEARING GEOMETRY: rects stay on TRUE EMPTY SCENERY (left/right edge
 * ridges + a thin sky strip under the topbar band + a thin horizon band above
 * the bottom rail). They must NOT cover the home/research working-surface
 * cards. Primary chrome (Topbar, NavRail, PanelLayout) wins stacking; edge
 * scenery remains hit-testable.
 *
 * PRODUCT ROUTES (click only — see sceneHotspotProductRoutes.ts):
 *   igloo-ridge      → /arcade  (Werner's igloo mini-games)
 *   horizon-journey  → /        (research door)
 *   peak-right       → /library (reading door)
 *   sky-aurora       → /home    (project front door)
 *   peak-left        → ambient  (reserved for shell-launch honesty proof)
 */

export type SceneHotspotId =
  | "peak-left"
  | "peak-right"
  | "sky-aurora"
  | "igloo-ridge"
  | "horizon-journey";

export interface SceneHotspot {
  id: SceneHotspotId;
  /** Normalized rect in [0,1] of the scene viewport (x, y, w, h). */
  norm: { x: number; y: number; w: number; h: number };
  label: string;
}

/**
 * Edge-scenery hotspot map. Widths stay ≤8% of the viewport on the sides so a
 * full-bleed working surface remains the primary click target in the center.
 * igloo-ridge sits in a lower-left scenery pocket (not center cards).
 */
export const SCENE_HOTSPOTS: readonly SceneHotspot[] = [
  {
    id: "sky-aurora",
    // Thin strip under topbar (~0.06–0.10), center X — falls through where
    // no button? This strip IS a button; keep narrow and below topbar height.
    norm: { x: 0.35, y: 0.07, w: 0.3, h: 0.035 },
    label: "Aurora sky",
  },
  {
    // Inset past the ad-border edge (~48px) so z-35 hotspots are not buried
    // under AdBorderMount (z≈150) on the extreme frame edge. Still a thin
    // left scenery ribbon, not the center cards.
    id: "peak-left",
    norm: { x: 0.055, y: 0.22, w: 0.055, h: 0.45 },
    label: "Left ridge",
  },
  {
    id: "peak-right",
    norm: { x: 0.89, y: 0.22, w: 0.055, h: 0.45 },
    label: "Right peak",
  },
  {
    id: "igloo-ridge",
    // Lower-left scenery pocket inset past ad border.
    norm: { x: 0.055, y: 0.7, w: 0.08, h: 0.1 },
    label: "Igloo ridge",
  },
  {
    id: "horizon-journey",
    // Thin band above bottom rail; avoids main content cards.
    norm: { x: 0.3, y: 0.885, w: 0.4, h: 0.025 },
    label: "Horizon path",
  },
] as const;

export interface PixelRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Project a normalized hotspot into CSS pixels for the current viewport. */
export function hotspotToPixels(
  hotspot: SceneHotspot,
  viewport: { width: number; height: number },
): PixelRect {
  const width = Math.max(1, viewport.width);
  const height = Math.max(1, viewport.height);
  return {
    x: hotspot.norm.x * width,
    y: hotspot.norm.y * height,
    w: hotspot.norm.w * width,
    h: hotspot.norm.h * height,
  };
}

/** Hit-test pointer (css px) against adaptive hotspots. */
export function hitTestHotspot(
  x: number,
  y: number,
  viewport: { width: number; height: number },
  hotspots: readonly SceneHotspot[] = SCENE_HOTSPOTS,
): SceneHotspot | null {
  for (const h of hotspots) {
    const r = hotspotToPixels(h, viewport);
    if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
      return h;
    }
  }
  return null;
}

/**
 * True when a normalized rect lives on empty scenery margins (left/right
 * edges or thin top/bottom bands) — not over the center working-surface
 * cards. Used by tests to pin the no-steal-primary-controls contract.
 */
export function isSceneryMarginHotspot(hotspot: SceneHotspot): boolean {
  const { x, y, w, h } = hotspot.norm;
  const right = x + w;
  const bottom = y + h;
  // Edge ribbons (including ad-border inset ~5–12%) or thin top/bottom bands.
  const onLeft = right <= 0.14;
  const onRight = x >= 0.86;
  const onTop = bottom <= 0.12;
  const onBottom = y >= 0.87;
  return onLeft || onRight || onTop || onBottom;
}
