/**
 * theme.ts — the one source of truth for appearance: theme and motion.
 *
 * The contract is shared with the pre-paint boot script in index.html:
 *
 *   localStorage 'antiek.theme'   light | dark | (absent = system)
 *   localStorage 'antiek.motion'  reduce | full | (absent = system)
 *   <html data-theme-pref>        the theme preference for this session
 *   <html data-theme>             the RESOLVED theme, light | dark (CSS + Tailwind dark: key on it)
 *   <html data-motion>            reduce | full, absent for system
 *
 * The attributes on <html> are the live state; storage only persists it. Every
 * reader (useTheme, useMotionPreference, usePrefersReducedMotion, the scene)
 * subscribes through `subscribeAppearance`, which follows the OS setting, the
 * setters below, and other tabs. Storage access is wrapped: private windows
 * and blocked storage keep the choice for the session instead of throwing.
 */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";
export type MotionPreference = "system" | "reduce" | "full";

export const THEME_KEY = "antiek.theme";
export const MOTION_KEY = "antiek.motion";
const DARK = "(prefers-color-scheme: dark)";
const REDUCE = "(prefers-reduced-motion: reduce)";

const html = () => document.documentElement;
const subscribers = new Set<() => void>();
const notify = () => subscribers.forEach((fn) => fn());
const media = (q: string) =>
  typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(q) : null;

function stored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function persist(key: string, value: string): void {
  try {
    if (value === "system") window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the preference still holds for this session */
  }
}

export function themePreference(): ThemePreference {
  if (typeof document === "undefined") return "system";
  const p = html().getAttribute("data-theme-pref") ?? stored(THEME_KEY);
  return p === "light" || p === "dark" ? p : "system";
}

export function resolvedTheme(): ResolvedTheme {
  const p = themePreference();
  if (p !== "system") return p;
  return media(DARK)?.matches ? "dark" : "light";
}

/** Write the resolved theme to <html> and sync the browser-chrome colour. */
export function applyTheme(pref: ThemePreference = themePreference()): void {
  const el = html();
  el.setAttribute("data-theme-pref", pref);
  el.setAttribute("data-theme", resolvedTheme());
  const meta = document.querySelector('meta[name="theme-color"]');
  const page = getComputedStyle(el).getPropertyValue("--bg-page").trim();
  if (meta && page) meta.setAttribute("content", page);
  notify();
}

export function setThemePreference(pref: ThemePreference): void {
  persist(THEME_KEY, pref);
  applyTheme(pref);
}

export function motionPreference(): MotionPreference {
  if (typeof document === "undefined") return "system";
  const m = html().getAttribute("data-motion") ?? stored(MOTION_KEY);
  return m === "reduce" || m === "full" ? m : "system";
}

/** The in-app choice wins; "system" defers to the OS setting. */
export function prefersReducedMotion(): boolean {
  const m = motionPreference();
  return m === "reduce" || (m === "system" && !!media(REDUCE)?.matches);
}

export function setMotionPreference(pref: MotionPreference): void {
  persist(MOTION_KEY, pref);
  if (pref === "system") html().removeAttribute("data-motion");
  else html().setAttribute("data-motion", pref);
  notify();
}

/** One set of OS/storage listeners for the whole app, however many readers. */
function listen(): () => void {
  const dark = media(DARK);
  const reduce = media(REDUCE);
  const onTheme = () => (themePreference() === "system" ? applyTheme("system") : notify());
  const onStorage = (e: StorageEvent) => {
    if (e.key === THEME_KEY) applyTheme(e.newValue === "light" || e.newValue === "dark" ? e.newValue : "system");
    if (e.key === MOTION_KEY) setMotionPreference(e.newValue === "reduce" || e.newValue === "full" ? e.newValue : "system");
  };
  dark?.addEventListener?.("change", onTheme);
  reduce?.addEventListener?.("change", notify);
  window.addEventListener("storage", onStorage);
  return () => {
    dark?.removeEventListener?.("change", onTheme);
    reduce?.removeEventListener?.("change", notify);
    window.removeEventListener("storage", onStorage);
  };
}
let unlisten: (() => void) | null = null;

/**
 * Subscribe to every appearance change: OS theme / reduced-motion, the
 * setters above, and other tabs (storage). A system theme change re-resolves
 * data-theme when the preference is system.
 */
export function subscribeAppearance(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  subscribers.add(onChange);
  unlisten ??= listen();
  return () => {
    subscribers.delete(onChange);
    if (!subscribers.size && unlisten) {
      unlisten();
      unlisten = null;
    }
  };
}
