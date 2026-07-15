import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import { emitWernerExperience } from "../werner";
import {
  SCENE_HOTSPOTS,
  hotspotToPixels,
  type SceneHotspot,
  type SceneHotspotId,
} from "./interactiveRegions";

/**
 * Viewport-adaptive interactive hotspot overlay for the living mountainscape.
 *
 * MUST mount at **shell level** (AppShell), not inside Scene z-0 — a
 * full-viewport chrome sibling with default pointer-events would otherwise
 * bury the buttons. Contract:
 *   - overlay root: `pointer-events: none` (empty space falls through)
 *   - each hotspot button: `pointer-events: auto` (real hit targets)
 *   - chrome column: `pointer-events: none` with `auto` only on interactive
 *     surfaces (Topbar, PanelLayout, NavRail, …) so hits reach hotspots where
 *     chrome does not claim them.
 *
 * Pure geometry comes from {@link hotspotToPixels} / {@link SCENE_HOTSPOTS}.
 */

export interface SceneHotspotsProps {
  /** Injectable viewport for unit tests; defaults to window size. */
  viewport?: { width: number; height: number };
  /** Called when a hotspot is activated (hover enter or click). */
  onActivate?: (id: SceneHotspotId, kind: "hover" | "click") => void;
  reducedMotion?: boolean;
  /**
   * Stacking mode:
   *   - "shell" (default) — fixed inset-0, z between scene paint and chrome
   *   - "inline" — absolute inset-0 for isolated unit tests without AppShell
   */
  mode?: "shell" | "inline";
}

function readViewport(): { width: number; height: number } {
  if (typeof window === "undefined") return { width: 1440, height: 900 };
  return { width: window.innerWidth, height: window.innerHeight };
}

export function SceneHotspots({
  viewport: viewportProp,
  onActivate,
  reducedMotion = false,
  mode = "shell",
}: SceneHotspotsProps) {
  const [viewport, setViewport] = useState(viewportProp ?? readViewport);
  const [hovered, setHovered] = useState<SceneHotspotId | null>(null);
  const [lastClick, setLastClick] = useState<SceneHotspotId | null>(null);
  // Living-TV: one curious glance per hotspot per mount (no hover spam).
  const hoverGlanced = useRef(new Set<SceneHotspotId>());

  useEffect(() => {
    if (viewportProp) {
      setViewport(viewportProp);
      return;
    }
    if (typeof window === "undefined") return;
    const onResize = () => setViewport(readViewport());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [viewportProp]);

  const activate = useCallback(
    (h: SceneHotspot, kind: "hover" | "click") => {
      onActivate?.(h.id, kind);
      if (kind === "hover") {
        setHovered(h.id);
        if (!hoverGlanced.current.has(h.id)) {
          hoverGlanced.current.add(h.id);
          // Ambient TV beat — scenery notice without navigation.
          emitWernerExperience("highlight");
        }
      }
      if (kind === "click") {
        setLastClick(h.id);
        // Product experience: interacting with the home of the penguin is a
        // curious glance (highlight-adjacent ambient), not a hard fail.
        emitWernerExperience("highlight");
      }
    },
    [onActivate],
  );

  // Shell: fixed ABOVE chrome paint (z-30) at z-35 so edge scenery buttons
  // are real hit targets. Root is pointer-events:none — center/topbar/nav
  // pixels with no button fall THROUGH to primary chrome underneath.
  // Hotspot rects are edge-only (interactiveRegions) so they never blanket
  // working-surface cards. Inline: absolute for unit tests.
  const rootStyle: CSSProperties =
    mode === "shell"
      ? {
          position: "fixed",
          inset: 0,
          zIndex: 35,
          pointerEvents: "none",
        }
      : {
          position: "absolute",
          inset: 0,
          zIndex: 5,
          pointerEvents: "none",
        };

  return (
    <div
      data-testid="scene-hotspots"
      data-hotspots-mode={mode}
      data-hovered={hovered ?? ""}
      data-last-click={lastClick ?? ""}
      data-hotspot-count={SCENE_HOTSPOTS.length}
      aria-hidden="false"
      style={rootStyle}
    >
      {SCENE_HOTSPOTS.map((h) => {
        const r = hotspotToPixels(h, viewport);
        const isHot = hovered === h.id || lastClick === h.id;
        return (
          <button
            key={h.id}
            type="button"
            data-testid={`scene-hotspot-${h.id}`}
            data-hotspot-id={h.id}
            aria-label={h.label}
            title={h.label}
            onMouseEnter={() => activate(h, "hover")}
            onMouseLeave={() => setHovered((cur) => (cur === h.id ? null : cur))}
            onFocus={() => activate(h, "hover")}
            onClick={() => activate(h, "click")}
            style={{
              position: "absolute",
              left: r.x,
              top: r.y,
              width: r.w,
              height: r.h,
              pointerEvents: "auto",
              cursor: "pointer",
              // Brand sun-yellow rim when hot (hover/focus/last-click) — living TV.
              border: isHot
                ? "1px solid rgba(245, 223, 36, 0.55)"
                : "1px solid transparent",
              borderRadius: 8,
              background: isHot
                ? "rgba(245, 223, 36, 0.08)"
                : "transparent",
              // Keyboard focus ring (sun) — visible without relying on browser default.
              outline: "none",
              boxShadow: isHot
                ? "0 0 0 2px rgba(245, 223, 36, 0.35)"
                : "none",
              transition: reducedMotion
                ? "none"
                : "background 160ms ease, border-color 160ms ease, box-shadow 160ms ease",
              padding: 0,
            }}
          />
        );
      })}
    </div>
  );
}

export default SceneHotspots;
