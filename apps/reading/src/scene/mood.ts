import type { SceneState } from "../api/krea";
import { resolvedTheme } from "../design/theme";

/**
 * Scene mood model (SPR-04, milestone 7 — day/night sync + milestone 4 — Krea
 * mood states).
 *
 * The app's day/night signal is the resolved theme on <html data-theme>
 * (src/design/theme.ts: the in-app Light / Dark / System preference, System
 * following the OS). Tailwind's `dark:` keys on the same attribute, so the
 * scene and the chrome can never disagree. `prefersDark()` below reads it for
 * non-React callers; the Scene itself subscribes through useTheme so it
 * re-renders when the theme changes without a reload.
 *
 * THEME → MOOD MAPPING (documented contract; drives BOTH the procedural sky
 * palette and the Krea prompt scene-state):
 *
 *   theme light  ->  daypart "day"   ->  mood "day"
 *   theme dark   ->  daypart "night" ->  mood "night"
 *
 * We model FOUR dayparts (dawn / day / dusk / night) so the Krea axis and the
 * procedural palette have room to evolve, but the app only emits a binary
 * light/dark signal today, so we map light→day and dark→night. Dawn/dusk are
 * reserved transitional moods a future time-of-day source can light up WITHOUT
 * changing this contract (they already have palettes + prompts). Until such a
 * source exists, the scene is deterministically day or night, in lockstep with
 * the app theme — change the theme and the whole scene (procedural + Krea
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

/** The app's resolved theme (in-app preference, else the OS). SSR-safe. */
export function prefersDark(): boolean {
  return resolvedTheme() === "dark";
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
