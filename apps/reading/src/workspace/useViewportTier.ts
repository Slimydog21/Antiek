import { useEffect, useState } from "react";

/**
 * Viewport-tier hook. Returns one of five tiers based on window width.
 * Components downstream (PanelLayout, NavRail, Topbar) collapse panels
 * + chrome at smaller tiers per docs/ui_redesign_posthog/sprint_11_a11y_responsive.html.
 *
 *   tier        width             behaviour
 *   xl          ≥ 1280            full: both docks visible, floating ok
 *   lg          ≥ 1024 < 1280     one dock at a time (right opens → left collapses)
 *   md          ≥ 768  < 1024     no docks; panels open as full-width overlays;
 *                                 floating disabled (snaps to overlay)
 *   sm          < 768             NavRail collapses; "open a larger screen" hint
 */
export type ViewportTier = "xl" | "lg" | "md" | "sm";

function tierFor(width: number): ViewportTier {
  if (width >= 1280) return "xl";
  if (width >= 1024) return "lg";
  if (width >= 768) return "md";
  return "sm";
}

export function useViewportTier(): ViewportTier {
  const [tier, setTier] = useState<ViewportTier>(() => {
    if (typeof window === "undefined") return "xl";
    return tierFor(window.innerWidth);
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const onResize = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        setTier(tierFor(window.innerWidth));
      }, 80);
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      if (timer) clearTimeout(timer);
    };
  }, []);

  return tier;
}
