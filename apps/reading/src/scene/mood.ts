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
 *   OS light + [05:30,08:00) local -> dawn; otherwise day
 *   OS dark  + [17:00,20:00) local -> dusk; otherwise night
 *
 * OS theme deliberately owns the light/dark band; wall time cannot override it.
 * The bounded windows are brand art direction rather than sunrise calculations,
 * keeping behavior predictable across latitude, weather, and travel.
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

/** Fixed local-civil-time ambience windows. These are deliberate Antiek art
 * direction, not astronomical sunrise/sunset estimates. Keeping them named
 * makes the product judgment reviewable and the timer authority injectable. */
export const DAWN_START_MINUTE = 5 * 60 + 30;
export const DAWN_END_MINUTE = 8 * 60;
export const DUSK_START_MINUTE = 17 * 60;
export const DUSK_END_MINUTE = 20 * 60;

export function moodFromThemeAndLocalMinutes(
  dark: boolean,
  localMinutes: number,
): SceneMood {
  if (
    !Number.isInteger(localMinutes) ||
    localMinutes < 0 ||
    localMinutes >= 24 * 60
  ) {
    throw new RangeError("localMinutes must be an integer in [0, 1440)");
  }
  const dayPart: DayPart = dark
    ? localMinutes >= DUSK_START_MINUTE && localMinutes < DUSK_END_MINUTE
      ? "dusk"
      : "night"
    : localMinutes >= DAWN_START_MINUTE && localMinutes < DAWN_END_MINUTE
      ? "dawn"
      : "day";
  return { dayPart, weather: "snow" };
}

/** Reuse the app's existing day/night signal (OS prefers-color-scheme).
 *  SSR-safe. This is the SAME query Settings + Tailwind `media` darkMode use. */
export function prefersDark(): boolean {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function"
  ) {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Legacy binary mapper retained for callers that explicitly need theme only. */
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
