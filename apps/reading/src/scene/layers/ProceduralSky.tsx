import { useMemo } from "react";

import type { SceneMood } from "../mood";
import { moodKey } from "../mood";
import { makeRidge, PEAK_BANDS, ridgePathD } from "../peaks";
import { fieldSeed } from "../field";
import { skyGradientClasses, ridgeFillClass } from "../landscapePalette";

/**
 * ProceduralSky (SPR-04, milestone 5 — the deterministic offline fallback).
 *
 * A hand-authored, intentional sky + peak silhouette that needs NO Krea, NO
 * network, NO key — drawn entirely from design tokens + a seeded ridge. This
 * is the path CI and the sandbox ALWAYS take (no Krea key), so it must look
 * deliberate, not a placeholder grey.
 *
 * DETERMINISM (snapshot-test contract): given a mood, the output is byte-stable
 * — the gradient classes are fixed per daypart and the peak paths come from the
 * pure `makeRidge(seed)`. No Date.now, no Math.random, no rAF. A snapshot of
 * this component for a fixed mood is identical across runs.
 *
 * COLOUR DISCIPLINE: every colour is a design token via Tailwind classes
 * (bg-*, fill-*, text-*) or a CSS `var(--token)` — NO raw hex (token-lint).
 * The sky gradient and ridge fills come from landscapePalette.ts, which maps
 * DayPart to Tailwind colour keys backed by tokens.css custom properties.
 */

export interface ProceduralSkyProps {
  mood: SceneMood;
  /** parallax y-shifts per band in px (already bounded by the Scene). */
  shifts?: number[];
}

/**
 * The CSS/SVG sky + peaks. `shifts` lets the Scene apply bounded parallax to
 * the peak bands without re-generating geometry (cheap transform).
 */
export function ProceduralSky({ mood, shifts }: ProceduralSkyProps) {
  const seed = fieldSeed(moodKey(mood));
  // Memoize the ridge geometry on the mood seed — pure, so this only recomputes
  // when the mood (and thus the scene) actually changes.
  const bands = useMemo(
    () =>
      PEAK_BANDS.map((b) => ({
        band: b,
        points: makeRidge((seed ^ b.seedOffset) >>> 0, b.ridge),
      })),
    [seed],
  );

  return (
    <div
      className={"absolute inset-0 " + skyGradientClasses(mood.dayPart)}
      data-testid="procedural-sky"
      data-mood={moodKey(mood)}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        focusable="false"
      >
        {bands.map(({ band, points }, i) => {
          const yShift = shifts?.[i] ?? 0;
          // Anchor the band lower on the canvas for nearer bands.
          const anchorShift = band.anchor * 18;
          return (
            <path
              key={i}
              d={ridgePathD(points, anchorShift + yShift)}
              className={ridgeFillClass(mood.dayPart, i)}
            />
          );
        })}
      </svg>
    </div>
  );
}

export default ProceduralSky;
