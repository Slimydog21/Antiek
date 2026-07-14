import type { DayPart } from "./mood";

/**
 * Landscape palette — six named colour roles per daypart (ATP-01 milestone 1).
 *
 * This is the SINGLE source of truth for the procedural sky gradient and ridge
 * fills. ProceduralSky consumes the token names and applies the correct
 * Tailwind utility prefix (from-/via-/to- for sky; fill- for ridges).
 *
 * The six roles:
 *   skyTop      — upper sky gradient stop (lightest / deepest)
 *   skyMid      — mid-sky gradient stop
 *   skyHorizon  — horizon gradient stop (the atmospheric hinge)
 *   ridgeFar    — farthest ridge band (lightest / most recessive)
 *   ridgeMid    — middle ridge band
 *   ridgeNear   — nearest ridge band (darkest / most prominent)
 *
 * Day and night values are byte-identical to the prior ProceduralSky classes.
 * Dawn and dusk introduce new atmospheric roles — cold glacial air with a
 * weathered-straw horizon at dawn; deep slate/indigo with a restrained
 * desaturated teal afterglow at dusk.
 *
 * Values are Tailwind colour keys (matching the names in tailwind.config.js
 * colours and tokens.css --scene-* vars). The component layer applies the
 * appropriate utility prefix.
 */

export interface LandscapeRoles {
  sky: string;
  ridges: readonly [string, string, string];
}

/**
 * The exhaustive six-role palette keyed by DayPart.
 *
 * Invariants:
 *   - All four DayPart keys exist.
 *   - All six tuples are unique (tested in landscapePalette.test.ts).
 *   - Day and night values are byte-identical to the pre-ATP-01 ProceduralSky
 *     classes.
 */
export const LANDSCAPE_PALETTE: Record<DayPart, LandscapeRoles> = {
  dawn: {
    sky: "bg-scene-dawn-sky",
    ridges: [
      "fill-scene-dawn-ridge-far",
      "fill-scene-dawn-ridge-mid",
      "fill-scene-dawn-ridge-near",
    ],
  },
  day: {
    sky: "bg-gradient-to-b from-glacial-1 via-ice-3 to-ice-1",
    ridges: ["fill-glacial-1", "fill-glacial-2", "fill-shadow-1"],
  },
  dusk: {
    sky: "bg-scene-dusk-sky",
    ridges: [
      "fill-scene-dusk-ridge-far",
      "fill-scene-dusk-ridge-mid",
      "fill-scene-dusk-ridge-near",
    ],
  },
  night: {
    sky: "bg-gradient-to-b from-space-2 via-space-1 to-charcoal-2",
    ridges: ["fill-charcoal-2", "fill-charcoal-1", "fill-space-1"],
  },
} as const;

/** Sky gradient classes for a given daypart. Returns the full Tailwind
 *  `bg-gradient-to-b from-… via-… to-…` string. */
export function skyGradientClasses(mood: DayPart): string {
  return LANDSCAPE_PALETTE[mood].sky;
}

/** Ridge fill class for a given band index (0 = far, 1 = mid, 2 = near). */
export function ridgeFillClass(mood: DayPart, band: number): string {
  const ridges = LANDSCAPE_PALETTE[mood].ridges;
  return ridges[band] ?? ridges[2];
}
