import { useEffect, useState } from "react";

/**
 * S11 — honour the operator's OS-level reduced-motion preference.
 *
 * Returns `true` when `prefers-reduced-motion: reduce` matches.
 * Subscribers re-render when the preference changes (e.g. operator
 * toggles macOS Accessibility settings without reloading).
 *
 * Consumers in S11:
 *   - PanelLayoutPanel framer-motion springs → `duration: 0`
 *   - PanelLayout dock width/height transitions → 0ms instead of 150ms
 *   - LemonToast slide-in → fade-in
 *   - Hover-lift translate transforms → no-op
 *
 * SSR-safe: returns `false` when window is undefined.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduce, setReduce] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (e: MediaQueryListEvent) => setReduce(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return reduce;
}
