import { useEffect, useState } from "react";

import type { SceneState } from "../api/krea";

/**
 * Scene mood model (SPR-04, milestone 7 — day/night sync + milestone 4 — Krea
 * mood states).
 *
 * The app's day/night signal is Tailwind's `darkMode: "media"` strategy
 * (tailwind.config.js) — i.e. the OS `prefers-color-scheme`. There is NO
 * app-level theme store or `.dark` class toggle (verified: Settings reads
 * `matchMedia("(prefers-color-scheme: dark)")` directly; AdBorder uses the
 * `dark:` variant). So we REUSE that exact signal — we do not invent a parallel
 * theme mechanism — via the tiny `prefersDark()` reader below.
 *
 * THEME → MOOD MAPPING (documented contract; drives BOTH the procedural sky
 * palette and the Krea prompt scene-state):
 *
 *   OS prefers-color-scheme = light  ->  daypart "day"   ->  mood "day"
 *   OS prefers-color-scheme = dark   ->  daypart "night" ->  mood "night"
 *
 * We model FOUR dayparts (dawn / day / dusk / night) so the Krea axis and the
 * procedural palette have room to evolve, but the app only emits a binary
 * light/dark signal today, so we map light→day and dark→night. Dawn/dusk are
 * reserved transitional moods a future time-of-day source can light up WITHOUT
 * changing this contract (they already have palettes + prompts). Until such a
 * source exists, the scene is deterministically day or night, in lockstep with
 * the OS theme — change the OS theme and the whole scene (procedural + Krea
 * mood prompt) follows.
 *
 * WEATHER is a second mood axis, currently fixed to "snow" (the Herzog
 * Antarctic motif — wind-driven snow is always on). It is a field so a future
 * weather source can vary it without a schema change.
 */

export type DayPart = "dawn" | "day" | "dusk" | "night";
export type Weather = "clear" | "snow";

export interface SceneMood {
  dayPart: DayPart;
  weather: Weather;
}

/** Reuse the app's existing day/night signal (OS prefers-color-scheme).
 *  SSR-safe. This is the SAME query Settings + Tailwind `media` darkMode use. */
export function prefersDark(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** The current mood derived from the app theme. Binary today (light→day,
 *  dark→night); dawn/dusk reserved for a future time-of-day source. */
export function moodFromTheme(dark: boolean = prefersDark()): SceneMood {
  return {
    dayPart: dark ? "night" : "day",
    weather: "snow",
  };
}

/** Map a mood to the SPR-02 `SceneState` (the Krea cache key + placeholder
 *  key). `mood` carries the daypart, `dayNight` the binary the placeholder
 *  darkens on, `season` the weather motif. Deterministic — same mood, same
 *  scene-state, so the Krea cache + placeholder stay stable. */
export function sceneStateFromMood(mood: SceneMood): SceneState {
  const isNight = mood.dayPart === "night" || mood.dayPart === "dusk";
  return {
    mood: mood.dayPart,
    dayNight: isNight ? "night" : "day",
    season: mood.weather === "snow" ? "winter" : "clear",
  };
}

/** A stable string key for a mood — used as the procedural RNG seed and the
 *  crossfade change-detector (art refreshes only when THIS changes). */
export function moodKey(mood: SceneMood): string {
  return `${mood.dayPart}|${mood.weather}`;
}

/**
 * useSceneMood — the LIVE scene mood, re-derived when the OS day/night signal
 * flips (ALC SPR-07 M1). Subscribers re-render when `prefers-color-scheme`
 * changes (e.g. the OS crosses sunset, or the operator toggles dark mode),
 * exactly the way `usePrefersReducedMotion` tracks the reduced-motion query.
 *
 * This is the SAME signal `Scene.tsx` paints the sky from — so a consumer of
 * THIS hook and the sky can never disagree about what time it is. It carries no
 * clock and no RNG: the mood is a pure function of the media-query match, and
 * the only "event" is the OS preference change the app already emits.
 *
 * SSR-safe: seeds from `prefersDark()` (false off-window) and no-ops without
 * matchMedia.
 */
export function useSceneMood(): SceneMood {
  const [dark, setDark] = useState<boolean>(() => prefersDark());

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setDark(e.matches);
    mql.addEventListener("change", handler);
    // Re-sync once on mount in case the preference changed between the initial
    // render's lazy seed and the effect firing (no missed transition).
    setDark(mql.matches);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return moodFromTheme(dark);
}
