import { useSyncExternalStore } from "react";
import type { CSSProperties } from "react";

export const READING_FONTS = [
  { id: "source-serif", name: "Source Serif 4", family: "Source Serif 4", stack: '"Source Serif 4", "Charter", Georgia, serif', description: "Warm, restrained book type. Antiek's default." },
  { id: "source-sans", name: "Source Sans 3", family: "Source Sans 3", stack: '"Source Sans 3", system-ui, sans-serif', description: "Open, quiet letterforms with a contemporary feel." },
  { id: "literata", name: "Literata", family: "Literata", stack: '"Literata", Georgia, serif', description: "A more literary rhythm, designed for long-form reading." },
  { id: "atkinson", name: "Atkinson Hyperlegible Next", family: "Atkinson Hyperlegible Next", stack: '"Atkinson Hyperlegible Next", system-ui, sans-serif', description: "Distinct letters and numbers, designed with low vision in mind." },
  { id: "system", name: "Classic system serif", family: "Georgia", stack: 'Georgia, "Times New Roman", serif', description: "Your device's familiar serif. No font download needed." },
] as const;

export type ReadingFontId = (typeof READING_FONTS)[number]["id"];
export interface ReadingTypographyPreferences {
  font: ReadingFontId;
  size: number;
  lineHeight: number;
  measure: number;
  letterSpacing: number;
}

export const TYPOGRAPHY_STORAGE_KEY = "antiek.reading-typography.v1";
export const DEFAULT_READING_TYPOGRAPHY: Readonly<ReadingTypographyPreferences> = {
  font: "source-serif", size: 20, lineHeight: 1.65, measure: 66, letterSpacing: 0,
};

export function readingFont(id: ReadingFontId) {
  return READING_FONTS.find((font) => font.id === id) ?? READING_FONTS[0];
}

function bounded(value: unknown, fallback: number, min: number, max: number) {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

export function parseReadingTypography(value: unknown): ReadingTypographyPreferences {
  if (typeof value !== "object" || value === null || !("version" in value) || value.version !== 1) {
    return { ...DEFAULT_READING_TYPOGRAPHY };
  }
  const font = "font" in value ? READING_FONTS.find((item) => item.id === value.font) : undefined;
  return {
    font: font?.id ?? DEFAULT_READING_TYPOGRAPHY.font,
    size: bounded("size" in value ? value.size : undefined, DEFAULT_READING_TYPOGRAPHY.size, 14, 32),
    lineHeight: bounded("lineHeight" in value ? value.lineHeight : undefined, 1.65, 1.4, 2.2),
    measure: "measure" in value ? [52, 66, 78].find((item) => item === value.measure) ?? 66 : 66,
    letterSpacing: "letterSpacing" in value ? [0, 0.03, 0.06].find((item) => item === value.letterSpacing) ?? 0 : 0,
  };
}

let snapshot: ReadingTypographyPreferences = { ...DEFAULT_READING_TYPOGRAPHY };
let cachedStorage: string | null | undefined;
const listeners = new Set<() => void>();

function getSnapshot(): ReadingTypographyPreferences {
  if (typeof window === "undefined") return snapshot;
  try {
    const raw = window.localStorage.getItem(TYPOGRAPHY_STORAGE_KEY);
    if (raw !== cachedStorage) {
      cachedStorage = raw;
      try {
        const value: unknown = JSON.parse(raw ?? "null");
        snapshot = parseReadingTypography(value);
      } catch { snapshot = { ...DEFAULT_READING_TYPOGRAPHY }; }
    }
  } catch { /* Blocked storage keeps the tab's live choice. */ }
  return snapshot;
}

function emit() {
  for (const listener of listeners) listener();
}

function onStorage(event: StorageEvent) {
  if (event.key !== null && event.key !== TYPOGRAPHY_STORAGE_KEY) return;
  // Ignore sessionStorage events. Access can itself fail in private/blocked contexts.
  try {
    if (event.storageArea && event.storageArea !== window.localStorage) return;
  } catch { return; }
  getSnapshot();
  emit();
}

function subscribe(listener: () => void) {
  if (listeners.size === 0) window.addEventListener("storage", onStorage);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
}

export function setReadingTypography(patch: Partial<ReadingTypographyPreferences>) {
  snapshot = parseReadingTypography({ ...getSnapshot(), ...patch, version: 1 });
  try {
    const raw = JSON.stringify({ ...snapshot, version: 1 });
    window.localStorage.setItem(TYPOGRAPHY_STORAGE_KEY, raw);
    cachedStorage = raw;
  } catch { /* The live choice remains available for this tab. */ }
  emit();
}

export function resetReadingTypography() {
  setReadingTypography(DEFAULT_READING_TYPOGRAPHY);
}

export function useReadingTypography() {
  return useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_READING_TYPOGRAPHY);
}

export function readingTypographyStyle(preferences: Readonly<ReadingTypographyPreferences>): CSSProperties {
  return {
    fontFamily: readingFont(preferences.font).stack,
    fontSize: `${preferences.size / 16}rem`,
    lineHeight: preferences.lineHeight,
    maxWidth: `${preferences.measure}ch`,
    letterSpacing: `${preferences.letterSpacing}em`,
  };
}
