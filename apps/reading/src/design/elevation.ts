/**
 * elevation.ts — stack depth → shadow tier + cascade offsets (FEEL-S1).
 *
 * Single contract for WorkspaceStore floating panels (opaque-chunky) and
 * windowsStore glass windows (glass-scene). Consumers wire in FEEL-S2/S3;
 * this module is pure data + class strings (Vitest-assertable).
 *
 * PostHog OSS footnote: MIT `frontend/src/layout/panel-layout/` is a fixed
 * shell (nav + tree + side panel), not a floating z-manager — we borrow
 * elevation *feel*, not their layout architecture.
 */

export type ChromeMode = "opaque-chunky" | "glass-scene";

/** Tailwind class strings aligned with tokens.css `--shadow-z1…z3`. */
/** Indices 0–3 map to stack depth tiers (z3 is the ceiling at depth ≥2). */
const OPAQUE_SHADOW_BY_DEPTH = [
  "shadow-z1 dark:shadow-z1-night",
  "shadow-z2 dark:shadow-z2-night",
  "shadow-z3 dark:shadow-z3-night",
  "shadow-z3 dark:shadow-z3-night",
] as const;

/** Glass windows: title-bar stamp only; depth does not scale body shadow. */
const GLASS_TITLEBAR_SHADOW = "shadow-z1 dark:shadow-z1-night";

/** Window open cascade — must stay in sync with `windowsStore` `cascadeRect`. */
export const CASCADE_WINDOW_STEP_PX = 28;
export const CASCADE_WINDOW_WRAP_PX = 224;

/** Panel floating open cascade — `panelLayoutLogic.initialFloatingRect`. */
export const CASCADE_PANEL_STEP_PX = 22;
export const CASCADE_PANEL_WRAP_PX = 200;

export type CascadeStore = "windows" | "panels";

/**
 * Map stack depth (0 = flat/docked or scene) to shadow classes.
 * Depth is clamped to [0, 3]. Focus rings are FEEL-S5; not included here.
 */
export function shadowForStackDepth(depth: number, mode: ChromeMode): string {
  if (mode === "glass-scene") {
    return GLASS_TITLEBAR_SHADOW;
  }
  const clamped = Math.max(0, Math.min(3, Math.round(depth)));
  return OPAQUE_SHADOW_BY_DEPTH[clamped];
}

/**
 * Pixel offset for the nth stacked surface so the prior edge stays visible.
 * Formulas match production stores today (do not drift silently).
 */
export function cascadeOffset(
  index: number,
  store: CascadeStore = "windows",
): { x: number; y: number } {
  const n = Math.max(0, Math.floor(index));
  if (store === "windows") {
    const step = (n * CASCADE_WINDOW_STEP_PX) % CASCADE_WINDOW_WRAP_PX;
    return { x: step, y: step };
  }
  const step = (n * CASCADE_PANEL_STEP_PX) % CASCADE_PANEL_WRAP_PX;
  return { x: step, y: step };
}

/** Surfaces that must never receive opaque-chunky stack chrome (documented exemptions). */
export const ELEVATION_EXEMPT_SURFACES = [
  "ResearchWorkstation dense IDE (/inv/:id center)",
  "GlassSurface scene landings",
  "Werner illustration layer",
] as const;