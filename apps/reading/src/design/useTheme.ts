import { useSyncExternalStore } from "react";

import {
  motionPreference,
  prefersReducedMotion,
  resolvedTheme,
  setMotionPreference,
  setThemePreference,
  subscribeAppearance,
  themePreference,
  type MotionPreference,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";

const themeSnapshot = () => `${themePreference()} ${resolvedTheme()}`;
const motionSnapshot = () => `${motionPreference()} ${prefersReducedMotion()}`;

/**
 * The app's theme, reactive to the in-app preference, the OS setting and other
 * tabs. Replaces one-shot matchMedia reads: a component using this re-renders
 * when the theme changes without a reload.
 */
export function useTheme(): {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  isDark: boolean;
  setPreference: (pref: ThemePreference) => void;
} {
  const [preference, resolved] = useSyncExternalStore(
    subscribeAppearance,
    themeSnapshot,
    () => "system light",
  ).split(" ") as [ThemePreference, ResolvedTheme];
  return { preference, resolved, isDark: resolved === "dark", setPreference: setThemePreference };
}

/** The in-app motion preference plus the effective answer (in-app choice, else OS). */
export function useMotionPreference(): {
  preference: MotionPreference;
  reduced: boolean;
  setPreference: (pref: MotionPreference) => void;
} {
  const [preference, reduced] = useSyncExternalStore(
    subscribeAppearance,
    motionSnapshot,
    () => "system false",
  ).split(" ") as [MotionPreference, string];
  return { preference, reduced: reduced === "true", setPreference: setMotionPreference };
}
