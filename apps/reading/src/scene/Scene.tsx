import type { SceneMood } from "./mood";
import { useDerivedSceneMood } from "./useDerivedSceneMood";
import { useSceneClock } from "./useSceneClock";
import { useSceneArt } from "./useSceneArt";
import { useSceneMomentCue, type SceneMomentCue } from "./useSceneMomentCue";
import type { SceneFetcher } from "../krea/useKreaScene";
import { useKreaStatus } from "../krea/useKreaStatus";
import { Peaks } from "./layers/Peaks";
import { Clouds } from "./layers/Clouds";
import { Snow } from "./layers/Snow";
import { PenguinJourney } from "./layers/PenguinJourney";
import { KreaArtLayer } from "./layers/KreaArtLayer";
import { SceneStatusBadge } from "./SceneStatusBadge";
// The scene's consolidated keyframes + reduced-motion guard (one motion home,
// sanctioned in motion.guard.test.ts) — see scene.css.
import "./scene.css";

/**
 * Scene — the living mountainscape compositor (SPR-04, milestone 1 + 7).
 *
 * ─── LAYER ORDER (back → front; documented contract) ─────────────────────
 *   z-0  ProceduralSky      sky gradient + far/mid/near peak silhouettes
 *                           (inside <Peaks/>, which adds bounded parallax)
 *   z-1  KreaArtLayer       periodic Krea art, crossfaded over the sky on
 *                           mood change; renders nothing in fallback
 *   z-2  Clouds             parallax cloud drift (canvas, off the scene clock)
 *   z-3  Snow               wind-driven snow flurry (canvas, scene clock)
 *   z-4  PenguinJourney     scenery penguin walking toward the horizon
 * ─────────────────────────────────────────────────────────────────────────
 * Peaks render FIRST (furthest back) and the penguin LAST so it walks in front
 * of the ridge but behind the glass content above the whole Scene.
 *
 * MOUNTING: the Scene is `position:absolute inset-0 z-0 pointer-events-none` —
 * it paints behind everything and never captures pointer events. AppShell
 * mounts it as the FIRST child of the shell frame (see AppShell.tsx); the glass
 * working surfaces float over it.
 *
 * THEME + TIME → MOOD: OS prefers-color-scheme remains the binary authority.
 * Local civil time only refines light into dawn during [05:30,08:00), and dark
 * into dusk during [17:00,20:00). Those are fixed Antiek ambience windows, not
 * astronomy. A theme or bounded-time transition updates both the procedural
 * palette and Krea mood key in lockstep; explicit `mood` overrides stay dormant.
 *
 * DEGRADATION LADDER (all seamless):
 *   live Krea  → KreaArtLayer paints art over the procedural sky
 *   fallback   → KreaArtLayer renders nothing; ProceduralSky is the picture
 *   reduced    → useSceneClock freezes (one static frame, no rAF); canvases
 *                paint once at FROZEN_T; CSS animations are paused
 *   hidden tab → the clock pauses (no canvas repaint, no churn)
 */

export interface SceneProps {
  /** Mount-time deterministic override for stories/tests. Do not toggle this
   * authority at runtime: doing so intentionally remounts the scene substrate. */
  mood?: SceneMood;
  /** Inject a Krea fetcher for tests; production uses the real client. */
  fetchScene?: SceneFetcher;
  /** Force reduced-motion for the canvas layers (tests). Defaults to the
   *  clock's own reduced-motion detection. */
  reducedMotion?: boolean;
  /**
   * One-way typed callback: Scene detects committed authored mood transitions
   * (`night → dawn`, first `non-dusk → dusk`) and transports the cue to the shell. The shell passes it to
   * PenguinMascot, the sole foreground arbiter. Scene never emits a false
   * cue on mount, StrictMode, identical rerender, weather-only change, explicit mood override,
   * or unmount. (SPR-22)
   */
  onWernerMoment?: (cue: SceneMomentCue) => void;
}

export function Scene({
  mood: moodProp,
  fetchScene,
  reducedMotion,
  onWernerMoment,
}: SceneProps) {
  // A component split makes the explicit override genuinely dormant: React's
  // hook-order rules are preserved without creating an unused theme listener
  // or semantic boundary timer in deterministic stories/tests.
  if (moodProp) {
    return (
      <SceneContent
        mood={moodProp}
        fetchScene={fetchScene}
        reducedMotion={reducedMotion}
      />
    );
  }
  return (
    <DerivedScene
      fetchScene={fetchScene}
      reducedMotion={reducedMotion}
      onWernerMoment={onWernerMoment}
    />
  );
}

function DerivedScene({
  fetchScene,
  reducedMotion,
  onWernerMoment,
}: Omit<SceneProps, "mood">) {
  const mood = useDerivedSceneMood();
  useSceneMomentCue(mood, onWernerMoment);
  return (
    <SceneContent
      mood={mood}
      fetchScene={fetchScene}
      reducedMotion={reducedMotion}
    />
  );
}

function SceneContent({
  mood,
  fetchScene,
  reducedMotion,
}: Required<Pick<SceneProps, "mood">> & Omit<SceneProps, "mood">) {
  // The single scene clock — running / frozen (reduced-motion) / paused
  // (hidden). The `frozen` flag flows to the layers so they render one static
  // frame and drop parallax/crossfade transitions.
  const clock = useSceneClock();
  const frozen = reducedMotion ?? clock.frozen;

  // Periodic, mood-gated Krea art (never per frame — see useSceneArt).
  const art = useSceneArt(mood, fetchScene);
  // Status is fetched once at scene mount, matching useKreaScene's
  // mount/state-key scheduling style rather than adding a polling loop.
  const kreaStatus = useKreaStatus();

  return (
    <div
      className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
      data-testid="scene-root"
      data-scene-mood={mood.dayPart}
      data-scene-clock={clock.t}
      data-scene-frozen={frozen ? "true" : "false"}
      data-scene-fallback={art.isFallback ? "true" : "false"}
      aria-hidden="true"
    >
      {/* z-0 sky + peaks (with bounded parallax) */}
      <Peaks mood={mood} frozen={frozen} clockMs={clock.t} />
      {/* z-1 periodic Krea art, crossfaded on mood change (nothing in fallback) */}
      <KreaArtLayer art={art} frozen={frozen} clockMs={clock.t} />
      {/* z-2 clouds (canvas) */}
      <Clouds mood={mood} reducedMotion={frozen} />
      {/* z-3 snow (canvas) */}
      <Snow mood={mood} reducedMotion={frozen} />
      {/* z-4 scenery penguin */}
      <PenguinJourney mood={mood} />
      <SceneStatusBadge
        status={kreaStatus.data}
        error={kreaStatus.status === "error" ? kreaStatus.error : null}
      />
    </div>
  );
}

export default Scene;
