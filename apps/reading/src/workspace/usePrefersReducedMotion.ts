import { useSyncExternalStore } from "react";

import { prefersReducedMotion, subscribeAppearance } from "../design/theme";

/**
 * S11 — should motion be reduced right now?
 *
 * `true` when the in-app Motion setting is "Reduce", or when it is "Match
 * system" and the OS asks for `prefers-reduced-motion: reduce`. "Full" keeps
 * app-driven motion on regardless of the OS. Subscribers re-render when either
 * source changes (Settings > Appearance, or the OS toggle, without a reload).
 *
 * Consumers: PanelLayoutPanel springs, PanelLayout dock transitions,
 * LemonToast, the scene clock, hover-lift transforms.
 *
 * SSR-safe: `false` when window is undefined.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribeAppearance, prefersReducedMotion, () => false);
}
