import { useMemo } from "react";

import { moodFromTheme, prefersDark, type SceneMood } from "./mood";
import { useSceneClock } from "./useSceneClock";
import { useSceneArt } from "./useSceneArt";
import type { SceneFetcher } from "../krea/useKreaScene";
import { Peaks } from "./layers/Peaks";
import { Mountainscape, PLANE_DEPTHS } from "./layers/Mountainscape";
import { Clouds } from "./layers/Clouds";
import { Snow } from "./layers/Snow";
import { PenguinJourney } from "./layers/PenguinJourney";
import { KreaArtLayer } from "./layers/KreaArtLayer";
import { useSceneDrift } from "./useSceneDrift";
// The scene's consolidated keyframes + reduced-motion guard (one motion home,
// sanctioned in motion.guard.test.ts) — see scene.css.
import "./scene.css";

/**
 * Scene — the living mountainscape compositor (SPR-04, milestone 1 + 7).
 *
 * ─── LAYER ORDER (back → front; documented contract) ─────────────────────
 *   z-0a ProceduralSky      layered atmosphere (multi-stop sky + horizon glow +
 *                           seeded stars) + backdrop ridge bands (inside
 *                           <Peaks/>, which adds bounded parallax). ELEVATED in
 *                           ALC SPR-05 M2.
 *   z-0b Mountainscape      foreground depth planes (far/mid/near + aerial
 *                           haze) — the terrain the penguin journeys across,
 *                           parallax-ready (typed seams). NEW in ALC SPR-05 M4.
 *   z-1  KreaArtLayer       periodic Krea art, crossfaded over the whole
 *                           procedural composition on mood change; renders
 *                           nothing in fallback (the always-on real path)
 *   z-2  Clouds             parallax cloud drift (canvas, off the scene clock)
 *   z-3  Snow               wind-driven snow flurry (canvas, scene clock)
 *   z-4  PenguinJourney     scenery penguin walking toward the horizon
 * ─────────────────────────────────────────────────────────────────────────
 * Peaks render FIRST (furthest back), the foreground terrain over it, and the
 * penguin LAST so it walks in front of the ridge but behind the glass content
 * above the whole Scene. Krea (when present) crossfades over the ENTIRE
 * procedural composition (sky + backdrop + foreground terrain).
 *
 * MOUNTING: the Scene is `position:absolute inset-0 z-0 pointer-events-none` —
 * it paints behind everything and never captures pointer events. AppShell
 * mounts it as the FIRST child of the shell frame (see AppShell.tsx); the glass
 * working surfaces float over it.
 *
 * THEME → MOOD: the mood comes from the app's EXISTING day/night signal (OS
 * prefers-color-scheme, the same `media` darkMode Tailwind uses) via
 * moodFromTheme(). Change the OS theme → the sky palette AND the Krea mood
 * prompt follow, in lockstep. No parallel theme mechanism. (mood.ts documents
 * the full mapping table.)
 *
 * DEGRADATION LADDER (all seamless):
 *   live Krea  → KreaArtLayer paints art over the procedural sky
 *   fallback   → KreaArtLayer renders nothing; ProceduralSky is the picture
 *   reduced    → useSceneClock freezes (one static frame, no rAF); canvases
 *                paint once at FROZEN_T; CSS animations are paused
 *   hidden tab → the clock pauses (no canvas repaint, no churn)
 */

export interface SceneProps {
  /** Override the derived mood (e.g. a future time-of-day source / tests). */
  mood?: SceneMood;
  /** Inject a Krea fetcher for tests; production uses the real client. */
  fetchScene?: SceneFetcher;
  /** Force reduced-motion for the canvas layers (tests). Defaults to the
   *  clock's own reduced-motion detection. */
  reducedMotion?: boolean;
}

export function Scene({ mood: moodProp, fetchScene, reducedMotion }: SceneProps) {
  // Derive the mood from the app theme unless overridden. Memoize on the dark
  // signal so the object identity is stable across renders (the art hook keys
  // its fetch on the mood KEY, but a stable ref avoids needless effect churn).
  const dark = prefersDark();
  const derivedMood = useMemo(() => moodFromTheme(dark), [dark]);
  const mood = moodProp ?? derivedMood;

  // The single scene clock — running / frozen (reduced-motion) / paused
  // (hidden). The `frozen` flag flows to the layers so they render one static
  // frame and drop parallax/crossfade transitions.
  const clock = useSceneClock();
  const frozen = reducedMotion ?? clock.frozen;

  // Periodic, mood-gated Krea art (never per frame — see useSceneArt).
  const art = useSceneArt(mood, fetchScene);

  // SPR-06 M4 — the parallax BREATH: slow, subtle, independent per-plane drift
  // driven off the SAME scene clock, fed to Mountainscape via its typed seams
  // (SPR-05's interface — we never touch the layer's internals). Frozen ⇒ static
  // identity seams (the designed reduced-motion pose).
  const driftSeams = useSceneDrift(PLANE_DEPTHS, frozen);

  return (
    <div
      className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
      data-testid="scene-root"
      data-scene-mood={mood.dayPart}
      data-scene-frozen={frozen ? "true" : "false"}
      data-scene-fallback={art.isFallback ? "true" : "false"}
      aria-hidden="true"
    >
      {/* z-0a layered atmosphere sky + backdrop ridge (with bounded parallax) */}
      <Peaks mood={mood} frozen={frozen} />
      {/* z-0b foreground depth planes; SPR-06 drives the breath via the typed seams */}
      <Mountainscape mood={mood} seams={driftSeams} />
      {/* z-1 periodic Krea art, crossfaded on mood change (nothing in fallback) */}
      <KreaArtLayer art={art} frozen={frozen} />
      {/* z-2 clouds (canvas) */}
      <Clouds mood={mood} reducedMotion={frozen} />
      {/* z-3 snow (canvas) */}
      <Snow mood={mood} reducedMotion={frozen} />
      {/* z-4 scenery penguin */}
      <PenguinJourney mood={mood} />
    </div>
  );
}

export default Scene;
