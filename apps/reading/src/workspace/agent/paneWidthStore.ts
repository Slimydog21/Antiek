/**
 * paneWidthStore.ts — the inset right pane's preferred width (SPR-07 M5;
 * refs patterns 4/5/6). ENTRY-SAFE: zustand + accountWorkspaceOwner only
 * (PanelLayout imports usePaneWidth); never a contracts value.
 *
 * Persistence copies persistence.ts:295-348 (custom hotkeys): an
 * account-scoped key, `schemaVersion: 1`, null key ⇒ no I/O, quota silent.
 * NEVER the layout-preset precedent (:363-424), which is unscoped. A
 * separate blob: no snapshot schema bump (decision 10).
 */
import { useEffect, useState, type RefObject } from "react";
import { create } from "zustand";

import { accountStorageKey } from "../../lib/accountWorkspaceOwner";

export const PANE_WIDTH_KEY = "antiek.agent.pane-width.v1";
/** The pane never goes below this (pattern 6's floor). */
export const PANE_MIN = 240;
/** The main pane's minimum (pattern 5). */
export const MAIN_MIN = 424;
/** One keyboard step (pattern 4). */
export const STEP = 32;
/** Releasing a drag under this closes the pane (pattern 6). */
export const COLLAPSE_THRESHOLD = 244;
/** PanelLayout's INSET_GAP: outer gap + the gap between the panes = 3 gaps. */
const INSET_GAP = 12;

export interface PersistedPaneWidth {
  schemaVersion: 1;
  width: number;
}

export function readPaneWidth(): number | null {
  if (typeof window === "undefined") return null;
  const key = accountStorageKey(PANE_WIDTH_KEY);
  if (key === null) return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || !("schemaVersion" in parsed) || parsed.schemaVersion !== 1) return null;
    const width = (parsed as { width?: unknown }).width;
    return typeof width === "number" && Number.isFinite(width) ? width : null;
  } catch {
    return null;
  }
}

export function writePaneWidth(width: number): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(PANE_WIDTH_KEY);
  if (key === null) return;
  try {
    window.localStorage.setItem(key, JSON.stringify({ schemaVersion: 1, width } satisfies PersistedPaneWidth));
  } catch {
    // quota / disabled: the in-memory width stands
  }
}

export function clearPaneWidth(): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(PANE_WIDTH_KEY);
  if (key === null) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

/** The widest the right pane may be without pushing the main pane under
 *  MAIN_MIN; when nothing fits, the right pane wins down to PANE_MIN. */
export function paneWidthMax(containerWidth: number, leftDockWidth: number): number {
  return Math.max(PANE_MIN, containerWidth - 3 * INSET_GAP - leftDockWidth - MAIN_MIN);
}

export function effectiveWidth(i: { preferred: number | null; containerWidth: number; leftDockWidth: number; defaultWidth: number }): number {
  if (i.preferred === null) return i.defaultWidth;
  return Math.min(paneWidthMax(i.containerWidth, i.leftDockWidth), Math.max(PANE_MIN, Math.round(i.preferred)));
}

interface PaneWidthState {
  /** null = the tier default. */
  preferred: number | null;
  hydrated: boolean;
  hydrate: () => void;
  setPreferred: (width: number | null) => void;
  reset: () => void;
}

export const usePaneWidthStore = create<PaneWidthState>()((set) => ({
  preferred: null,
  hydrated: false,
  hydrate: () => set({ preferred: readPaneWidth(), hydrated: true }),
  setPreferred: (width) => {
    if (width === null) clearPaneWidth();
    else writePaneWidth(width);
    set({ preferred: width });
  },
  reset: () => set({ preferred: null, hydrated: false }),
}));

/** The container's live width (ResizeObserver; window.innerWidth where
 *  none exists, as in jsdom). */
export function useContainerWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(() => (typeof window === "undefined" ? 1280 : window.innerWidth));
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (typeof w === "number" && w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return width;
}

/** The inset right pane's width for PanelLayout: the preferred width
 *  clamped to the container, or null for the tier default. */
export function usePaneWidth(i: { leftDockWidth: number; containerRef: RefObject<HTMLElement | null>; defaultWidth: number }): { width: number; max: number } {
  const preferred = usePaneWidthStore((s) => s.preferred);
  const hydrated = usePaneWidthStore((s) => s.hydrated);
  const containerWidth = useContainerWidth(i.containerRef);
  useEffect(() => {
    if (!hydrated) usePaneWidthStore.getState().hydrate();
  }, [hydrated]);
  return {
    width: effectiveWidth({ preferred, containerWidth, leftDockWidth: i.leftDockWidth, defaultWidth: i.defaultWidth }),
    max: paneWidthMax(containerWidth, i.leftDockWidth),
  };
}
