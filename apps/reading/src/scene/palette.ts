import type { SceneMood } from "./mood";

/**
 * Scene palette resolver (SPR-04).
 *
 * COLOUR DISCIPLINE (token-lint contract): this file contains NO raw colour
 * literals. The canvas painters (Clouds / Snow) need concrete colour STRINGS
 * to draw with, but Canvas can't read Tailwind classes. So we read the SAME
 * design tokens the rest of the app uses straight off the document's computed
 * styles (the CSS custom properties defined in src/design/tokens.css, which
 * already mode-swap under prefers-color-scheme). One source of truth, no
 * parallel palette, and nothing for token-lint to flag.
 *
 * SSR / test-safe: when there is no document (or jsdom returns nothing), the
 * resolver returns CSS `var(--token)` strings as a graceful, still-token-driven
 * fallback. Canvas can't paint a `var()` string, but the only place these are
 * consumed is inside a real browser paint loop; the snapshot/fallback tests use
 * the CSS-gradient layers (ProceduralSky), not the canvas painters.
 */

/** The named tokens the scene paints with. Values are CSS var names so a
 *  reader either resolves them off :root or hands back the `var(--x)` form. */
const SCENE_TOKENS = {
  /** snow flake / cloud highlight — the lightest surface in the ramp. */
  flake: "--ice-0",
  /** cloud body — a soft mid surface. */
  cloud: "--ice-1",
  /** far haze — a cooler recessive surface. */
  haze: "--glacial-1",
} as const;

export type SceneTokenName = keyof typeof SCENE_TOKENS;

/** Resolve a scene token to a concrete colour string off the document's
 *  computed :root styles, or the `var(--x)` form when no document. */
export function resolveToken(name: SceneTokenName): string {
  const cssVar = SCENE_TOKENS[name];
  if (
    typeof document !== "undefined" &&
    typeof getComputedStyle === "function" &&
    document.documentElement
  ) {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(cssVar)
      .trim();
    if (v) return v;
  }
  return `var(${cssVar})`;
}

/** Per-mood alpha for the snow + clouds, so night snow is a touch dimmer than
 *  the bright day blizzard. Pure numbers (opacity), not colours. */
export function moodAlpha(mood: SceneMood): { snow: number; cloud: number } {
  const night = mood.dayPart === "night" || mood.dayPart === "dusk";
  return night ? { snow: 0.5, cloud: 0.22 } : { snow: 0.78, cloud: 0.34 };
}
