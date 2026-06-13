/**
 * wernerMoments.ts — Werner's deterministic delight moments (ALC SPR-07 M2).
 *
 * Character is not just a resting pose per weather (M1) — it is Werner NOTICING
 * a change. When the world shifts (the day turns to night, the light starts to
 * go at dusk), a focused reader's attention is already loose for that instant;
 * THAT is the only moment a small one-shot delight beat is allowed to play. The
 * rest of the time Werner is simply, calmly present (M1's resting cue).
 *
 * ─── THE HARD EDGE: every moment is a PURE STATE TRANSITION ───────────────────
 *
 * A moment fires off a transition between two scene states — `(prev, next)` —
 * NOTHING else. No Math.random (a delight that fires randomly is noise you can't
 * test or replay). No Date.now / wall-clock outside the scene clock the caller
 * already owns (a delight on a timer is a distraction with no cause). Because the
 * trigger is a pure function of two scene_keys, every moment is:
 *   • detectable  — `momentForTransition(prev, next)` returns it or null;
 *   • testable    — drive the exact transition, assert the exact moment;
 *   • replayable  — the same two states ALWAYS produce the same beat.
 *
 * ─── SUBTLE BY DESIGN (the minimalist steelman, answered) ─────────────────────
 *
 * The strongest argument against any of this is: Werner as a pure static mark
 * maximises reading focus; every animation is a tax on attention. The answer is
 * NOT "but delight is nice" — it is structural: a moment fires ONLY at a scene
 * TRANSITION (when the reader's eye is already leaving the text because the WORLD
 * changed), it is a ONE-SHOT (it ends; it does not loop in the reader's
 * periphery), and under reduced-motion it collapses to a designed STATIC pose
 * (no involuntary motion at all). A moment that fired mid-read, looped, or had no
 * trigger would be losing to the steelman and must be cut. If a built moment
 * keeps catching the builder's OWN eye while reading, it is cut (rigor #2).
 *
 * ─── MOTION OWNERSHIP ─────────────────────────────────────────────────────────
 *
 * This file decides WHEN a beat fires and WHICH sanctioned pose + how long it
 * runs — sourced from sceneMotion.ts tokens (no raw durations). It does NOT
 * author keyframes (SPR-06 owns motion mechanics) and does NOT add a 5th Werner
 * mood (the pose is always one of the four; the restraint guard holds).
 */
import type { SceneMood } from "../scene/mood";
import type { WernerMood } from "../design/tokens";
import { wernerForScene, type WernerSceneCue } from "./wernerSceneMap";
import { sceneDurationMs } from "../design/motion/sceneMotion";
import { durationMs } from "../design/motion";

/** A stable id per moment so a consumer can key/throttle + a test can name it. */
export type WernerMomentId =
  | "nightfall"
  | "daybreak"
  | "dusk-settle"
  | "fallback-unbothered";

/**
 * A delight moment: the one-shot beat that plays at a scene transition. It names
 * the SANCTIONED pose to flash, the duration (a sceneMotion token, never a raw
 * number), and the REDUCED-MOTION static pose it collapses to — so the moment is
 * fully designed for reduced-motion as a quiet pose change with no motion.
 */
export interface WernerMoment {
  id: WernerMomentId;
  /** The sanctioned Werner mood the one-shot flashes (one of the four). */
  pose: WernerMood;
  /** The pose Werner settles back to after the beat — the new resting cue. */
  settlesTo: WernerMood;
  /** Beat duration in ms, sourced from sceneMotion tokens (no raw literal). */
  durationMs: number;
  /**
   * Under prefers-reduced-motion the moment is NOT animated — it reads as a
   * brief static pose change (or, for the calmest moments, no change at all).
   * This is the designed reduced-state, not an afterthought.
   */
  reducedPose: WernerMood;
  /** Why this transition earns a beat — §5-voice, taste-checkable. */
  reason: string;
}

/** Is this dayPart a "lit" part of the cycle (day) vs a dark one (night)? */
function isNightDay(part: SceneMood["dayPart"]): "night" | "day" | "edge" {
  if (part === "night") return "night";
  if (part === "day") return "day";
  return "edge"; // dawn / dusk are the transitions, handled explicitly
}

/**
 * The pure transition resolver: given the PREVIOUS scene mood and the CURRENT
 * one, the delight moment (if any) that this exact change earns. Returns null
 * when the change does not cross a meaningful boundary (e.g. a phase drift that
 * keeps the same dayPart, or no change at all) — silence is the default, beats
 * are rare.
 *
 * TOTAL + PURE: every (prev, next) pair returns a moment or null, deterministic,
 * no clock, no RNG.
 */
export function momentForTransition(
  prev: SceneMood | null,
  next: SceneMood,
): WernerMoment | null {
  // First ever resolve (no prior state) is NOT a moment — Werner just appears in
  // his resting cue. A beat needs a CHANGE to react to.
  if (!prev) return null;
  // No change ⇒ no beat (this also makes a phase-drift that keeps the dayPart a
  // no-op, so the beat never fires per-frame).
  if (prev.dayPart === next.dayPart && prev.weather === next.weather) return null;

  const restNext = wernerForScene(next).mood;
  const fromState = isNightDay(prev.dayPart);
  const toState = isNightDay(next.dayPart);

  // ── Nightfall: the light goes (day → night). The calmest, most-earned beat:
  // the world just changed the most it can change. Werner settles for the night.
  if (fromState !== "night" && toState === "night") {
    return {
      id: "nightfall",
      pose: "thinking", // a contemplative tilt as the dark arrives, then settle
      settlesTo: restNext, // idle (the night resting cue)
      durationMs: sceneDurationMs.crossfade, // moves WITH the sky's crossfade
      reducedPose: restNext, // reduced-motion: just settle into the night pose
      reason:
        "The day turned to night — Werner takes a beat to notice the dark arrive, then settles. The reader's eye is already on the changing sky.",
    };
  }

  // ── Daybreak: the light returns (night → day). A small lift as the day comes.
  if (fromState === "night" && toState === "day") {
    return {
      id: "daybreak",
      pose: "celebrate", // a brief raised-flipper lift — the day is back
      settlesTo: restNext, // idle (the day resting cue)
      // The signature-beat ceiling (tokens.ts motion.duration.slow = 800ms,
      // == Werner's celebrate one-shot), sourced via motion.ts's parsed helper
      // so the lift can never out-run the longest sanctioned flourish.
      durationMs: durationMs.slow,
      reducedPose: restNext, // reduced-motion: settle straight into day idle
      reason:
        "Night gave way to day — a single quiet lift as the light returns, then back to calm. Fires only on the sky's flip, never mid-read.",
    };
  }

  // ── Dusk settle: the light STARTS to go (→ dusk). The contemplative beat that
  // matches dusk's resting cue (thinking). Subtle: the pose it flashes IS where
  // it settles, so the beat is a gentle arrival into the dusk tilt, not a costume
  // change. (Dusk is inert today — SPR-06 phase-drift lights it — so this is
  // designed-ahead, exercised only by the test driving the transition.)
  if (prev.dayPart !== "dusk" && next.dayPart === "dusk") {
    return {
      id: "dusk-settle",
      pose: "thinking",
      settlesTo: restNext, // thinking (dusk resting cue)
      durationMs: sceneDurationMs.light,
      reducedPose: restNext,
      reason:
        "The light began to fade into dusk — Werner eases into a watching tilt. The beat and the resting pose are the same, so it reads as arrival, not performance.",
    };
  }

  // CUT (rigor #2 — the minimalist steelman won this one): a "weather-clears"
  // beat (snow ⇄ clear within the same dayPart) was built and removed. Its pose
  // equalled its resting pose, so it changed nothing and animated nothing — a
  // no-op wearing the name of a moment. A delight that does nothing is exactly
  // the attention tax the minimalist argument warns about, with none of the
  // payoff, so it is not shipped. A weather change quietly updates the resting
  // cue (M1); no separate beat is earned.
  //
  // Any other dayPart edge (e.g. a dawn arrival, or dusk→night which nightfall
  // already owns) settles quietly with no special beat — the resting cue change
  // is enough.
  return null;
}

/**
 * The fallback beat (M2 — the "unbothered by missing art" moment). When the
 * Krea art for a scene fails to resolve and only the procedural floor is
 * painted, Werner is DELIBERATELY unbothered: he holds his calm resting pose, as
 * if the procedural scene were entirely normal — because it IS (the procedural
 * floor is a first-class surface, never "degraded"). This is a MOMENT in the
 * sense that it is an authored, deterministic response to a state (art absent),
 * not a random or timed one. There is no flourish to suppress under reduced
 * motion because there is no flourish at all — the calm is the point.
 *
 * Returns the resting cue unchanged, tagged so a consumer + the M3 copy can
 * treat the procedural scene as normal rather than apologise for it.
 */
export interface FallbackBeat {
  id: "fallback-unbothered";
  /** The calm resting pose — exactly what Werner shows when art IS present. */
  cue: WernerSceneCue;
  reason: string;
}

export function fallbackBeat(scene: SceneMood): FallbackBeat {
  return {
    id: "fallback-unbothered",
    cue: wernerForScene(scene),
    reason:
      "The painted art isn't there, only the procedural scene — and that is normal, not degraded. Werner holds his calm resting pose; there is nothing to apologise for and nothing to animate.",
  };
}
