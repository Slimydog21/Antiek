import { useEffect, useMemo, useState } from "react";

import {
  DAWN_END_MINUTE,
  DAWN_START_MINUTE,
  DUSK_END_MINUTE,
  DUSK_START_MINUTE,
  moodFromThemeAndLocalMinutes,
  moodKey,
  type SceneMood,
} from "./mood";

const COLOR_SCHEME_QUERY = "(prefers-color-scheme: dark)";

type TimerHandle = number;

export interface DerivedSceneMoodEnvironment {
  now(): Date;
  matchMedia(query: string): MediaQueryList;
  setTimeout(callback: () => void, delayMs: number): TimerHandle;
  clearTimeout(handle: TimerHandle): void;
  document: Pick<
    Document,
    "hidden" | "addEventListener" | "removeEventListener"
  >;
}

function browserEnvironment(): DerivedSceneMoodEnvironment | null {
  if (
    typeof window === "undefined" ||
    typeof document === "undefined" ||
    typeof window.matchMedia !== "function"
  ) {
    return null;
  }
  return {
    now: () => new Date(),
    matchMedia: (query) => window.matchMedia(query),
    setTimeout: (callback, delayMs) => window.setTimeout(callback, delayMs),
    clearTimeout: (handle) => window.clearTimeout(handle),
    document,
  };
}

function localMinutes(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

export function deriveSceneMood(dark: boolean, now: Date): SceneMood {
  return moodFromThemeAndLocalMinutes(dark, localMinutes(now));
}

/** Milliseconds until the next boundary that can change the current OS band.
 * A fresh local Date is built for every candidate so DST/timezone rules remain
 * browser-owned. Callback delivery is only a wake-up hint; the hook always
 * re-derives from a fresh Date rather than applying the intended boundary. */
export function nextSceneMoodBoundaryDelayMs(dark: boolean, now: Date): number {
  const boundaries = dark
    ? [DUSK_START_MINUTE, DUSK_END_MINUTE]
    : [DAWN_START_MINUTE, DAWN_END_MINUTE];
  const candidates = boundaries.map((minute) => {
    const next = new Date(now);
    next.setHours(Math.floor(minute / 60), minute % 60, 0, 0);
    if (next.getTime() <= now.getTime()) next.setDate(next.getDate() + 1);
    return next.getTime() - now.getTime();
  });
  return Math.max(1, Math.min(...candidates));
}

export function useDerivedSceneMood(
  injectedEnvironment?: DerivedSceneMoodEnvironment,
): SceneMood {
  const environment = useMemo(
    () => injectedEnvironment ?? browserEnvironment(),
    [injectedEnvironment],
  );
  const media = useMemo(
    () => environment?.matchMedia(COLOR_SCHEME_QUERY) ?? null,
    [environment],
  );
  const [mood, setMood] = useState<SceneMood>(() => {
    if (!environment || !media) return { dayPart: "day", weather: "snow" };
    return deriveSceneMood(media.matches, environment.now());
  });

  useEffect(() => {
    if (!environment || !media) return;
    let timer: TimerHandle | null = null;
    let disposed = false;

    const clearTimer = () => {
      if (timer !== null) environment.clearTimeout(timer);
      timer = null;
    };
    const publishCurrent = (now: Date) => {
      const next = deriveSceneMood(media.matches, now);
      setMood((current) =>
        moodKey(current) === moodKey(next) ? current : next,
      );
    };
    const arm = (now: Date = environment.now()) => {
      clearTimer();
      if (disposed || environment.document.hidden) return;
      timer = environment.setTimeout(
        () => {
          timer = null;
          if (disposed || environment.document.hidden) return;
          recomputeAndArm();
        },
        nextSceneMoodBoundaryDelayMs(media.matches, now),
      );
    };
    const recomputeAndArm = () => {
      // Derivation and scheduling share one snapshot; separate reads can
      // straddle an edge, publish the old mood, then schedule past that edge.
      const now = environment.now();
      publishCurrent(now);
      arm(now);
    };
    const onVisibilityChange = () => {
      if (environment.document.hidden) clearTimer();
      else recomputeAndArm();
    };

    media.addEventListener("change", recomputeAndArm);
    environment.document.addEventListener(
      "visibilitychange",
      onVisibilityChange,
    );
    recomputeAndArm();
    return () => {
      disposed = true;
      clearTimer();
      media.removeEventListener("change", recomputeAndArm);
      environment.document.removeEventListener(
        "visibilitychange",
        onVisibilityChange,
      );
    };
  }, [environment, media]);

  return mood;
}
