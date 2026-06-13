import { useMemo } from "react";

import type { SceneMood } from "../mood";
import { moodKey } from "../mood";
import { makeRidge, PEAK_BANDS, ridgePathD } from "../peaks";
import { fieldSeed, makeStars } from "../field";
import { atmosphereFor, hasStars } from "../palette";

/**
 * ProceduralSky (SPR-04 milestone 5 — the deterministic offline fallback;
 * ELEVATED in ALC SPR-05 M2 — sky = layered light, per dayPart anchor).
 *
 * A hand-authored, intentional sky + peak silhouette that needs NO Krea, NO
 * network, NO key — drawn entirely from design tokens + a seeded ridge + a
 * seeded star field. This is the path CI and the sandbox ALWAYS take (no Krea
 * key), so it IS the experience every user sees. It must look deliberate and
 * ATMOSPHERIC, not a flat gradient placeholder.
 *
 * ─── SPR-05 M2: layered atmosphere (per dayPart anchor) ───────────────────
 * The sky is no longer a 3-stop Tailwind class; it is composed of LAYERS, back
 * to front:
 *   1. SKY GRADIENT  — a 4-stop vertical ramp (zenith → horizon) from the
 *      per-dayPart `--scene-sky-*` tokens. Four distinct anchors (dawn/day/
 *      dusk/night) so SPR-06 can drift the light THROUGH the day.
 *   2. HORIZON GLOW  — a soft radial pool of `--scene-glow-*` at the skyline
 *      (warm weathered straw at dawn/dusk, cool at day/night) — the band of
 *      light where the sun/moon sits, the single biggest "this is a real sky"
 *      cue a flat gradient lacks.
 *   3. STARS         — at dusk + night only, a DETERMINISTIC seeded field
 *      (makeStars(fieldSeed(scene_key)) — never Math.random) of static SVG
 *      circles in the upper sky, above the ridge.
 *   4. PEAKS + HAZE  — the three seeded ridge bands, far → near, with an
 *      ATMOSPHERIC HAZE veil drawn between the far and mid bands (aerial
 *      perspective: distant peaks wash toward the haze colour). The haze is a
 *      `--scene-haze-*` token at low opacity, so far peaks recede.
 *
 * DETERMINISM (snapshot-test contract): given a mood, the output is byte-stable
 * — the gradient/glow are fixed per dayPart, the peak paths come from pure
 * `makeRidge(seed)`, and the stars from pure `makeStars(seed)`. No Date.now, no
 * Math.random, no rAF. A snapshot for a fixed mood is identical across runs.
 *
 * COMPOSITOR-FRIENDLY (SPR-06 seam, NOT animated here): the glow + star layers
 * carry an `opacity` and the whole sky composes via transform-able layers. SPR-06
 * can crossfade between two ProceduralSky renders (dayPart anchors) by animating
 * OPACITY only — no layout, no new geometry. This file animates NOTHING and adds
 * NO @keyframes (motion is SPR-06's; new keyframes also trip motion.guard).
 *
 * COLOUR DISCIPLINE: every colour is a design token — Tailwind classes (fill-*)
 * for the peaks, or a CSS `var(--scene-*)` for the sky/glow/haze/stars. NO raw
 * hex anywhere (token-lint). All `--scene-*` tokens mode-swap in tokens.css.
 */

/** Per-band peak fill, in token classes, far (lightest/most-recessive) → near
 *  (darkest). Day uses the ice ramp; night/dusk the space ramp; dawn the cool
 *  glacial ramp warming toward the near band. */
function peakFill(mood: SceneMood, band: number): string {
  switch (mood.dayPart) {
    case "night":
      return ["fill-charcoal-2", "fill-charcoal-1", "fill-space-1"][band] ?? "fill-space-1";
    case "dusk":
      // Twilight peaks: a touch lighter at the far band than full night.
      return ["fill-glacial-2", "fill-charcoal-2", "fill-charcoal-1"][band] ?? "fill-charcoal-1";
    case "dawn":
      // Pre-light peaks: cool glacial silhouettes, the near band the darkest.
      return ["fill-glacial-2", "fill-shadow-1", "fill-shadow-2"][band] ?? "fill-shadow-2";
    case "day":
    default:
      return ["fill-glacial-1", "fill-glacial-2", "fill-shadow-1"][band] ?? "fill-shadow-1";
  }
}

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
  const key = moodKey(mood);
  const seed = fieldSeed(key);
  const atmo = atmosphereFor(mood.dayPart);

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

  // Seeded star field — only composed for the anchors that paint stars
  // (dusk/night). Memoized on the seed so it is byte-stable + recomputes only
  // on a real scene change. Salt distinct from the peak/snow streams (field.ts).
  const stars = useMemo(
    () => (hasStars(mood.dayPart) ? makeStars(seed) : []),
    [seed, mood.dayPart],
  );

  // The 4-stop sky ramp as a single linear-gradient of token vars (zenith→horizon).
  const skyGradient =
    `linear-gradient(to bottom, ${atmo.sky[0]} 0%, ${atmo.sky[1]} 38%, ` +
    `${atmo.sky[2]} 68%, ${atmo.sky[3]} 100%)`;
  // The horizon glow: a soft elliptical pool of the glow token at the skyline,
  // fading to transparent upward. radial-gradient keeps it a band, not a wash.
  const glowGradient =
    `radial-gradient(120% 60% at 50% 100%, ${atmo.glow} 0%, transparent 62%)`;

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      data-testid="procedural-sky"
      data-mood={key}
      data-daypart={mood.dayPart}
      aria-hidden="true"
    >
      {/* layer 1 — the multi-stop sky ramp (token vars only). */}
      <div
        className="absolute inset-0"
        data-sky-layer="gradient"
        style={{ background: skyGradient }}
      />
      {/* layer 2 — the horizon glow pool (token var). Opacity-keyed so SPR-06
          can fade it; static here. */}
      <div
        className="absolute inset-0"
        data-sky-layer="glow"
        style={{ background: glowGradient, opacity: 0.75 }}
      />

      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        focusable="false"
      >
        {/* layer 3 — seeded stars (dusk/night only), above the ridge. Static
            circles; the colour is a token var via fill, the field is seeded. */}
        {stars.length > 0 && (
          <g data-sky-layer="stars">
            {stars.map((s, i) => (
              <circle
                key={i}
                cx={(s.x * 100).toFixed(3)}
                cy={(s.y * 100).toFixed(3)}
                r={(s.r * 0.16).toFixed(3)}
                fill={atmo.star}
                opacity={s.alpha.toFixed(3)}
              />
            ))}
          </g>
        )}

        {bands.map(({ band, points }, i) => {
          const yShift = shifts?.[i] ?? 0;
          // Anchor the band lower on the canvas for nearer bands.
          const anchorShift = band.anchor * 18;
          const d = ridgePathD(points, anchorShift + yShift);
          return (
            <g key={i} data-band={i}>
              <path d={d} className={peakFill(mood, i)} />
              {/* layer 4 — atmospheric HAZE between the far + mid bands: a
                  recessive veil that washes the FAR band toward the haze colour
                  (aerial perspective). Drawn over the far band only (i===0) at
                  low opacity. Token var fill; no animation. */}
              {i === 0 && (
                <path
                  d={d}
                  data-sky-layer="haze"
                  fill={atmo.haze}
                  opacity={0.34}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default ProceduralSky;
