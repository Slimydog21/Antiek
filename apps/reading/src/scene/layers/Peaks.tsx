import { useCallback, useEffect, useRef } from "react";

import type { SceneMood } from "../mood";
import { peakBandShiftPx, peakBandTransform, PEAK_BANDS } from "../peaks";
import { subscribeSceneClock } from "../useSceneClock";
import { ProceduralSky } from "./ProceduralSky";
import { sceneLayerTransform } from "../../design/motion/sceneMotion";

/**
 * Peaks (SPR-04, milestone 2 — subtle peak parallax).
 *
 * Renders the procedural sky+peaks (ProceduralSky owns the geometry) and adds
 * BOUNDED pointer parallax: as the pointer moves down the viewport the peak
 * bands shift a little, far bands less than near bands, giving depth without
 * nausea. A slow ambient drift rides on top.
 *
 * ANTI-NAUSEA BOUND (acceptance criterion): the pointer shift is capped at
 * MAX_PARALLAX_PX (±8 CSS px) and scaled by each band's `depth`, whatever the
 * viewport height; the ambient drift adds at most DRIFT.peaks.yAmplitudePx.
 * e2e/scene-parallax.spec.ts measures the rendered ridge to hold this.
 *
 * COST: no React state and no loop of its own. The pointer listener only
 * records a target; easing, drift and the band transforms are written on the
 * scene heartbeat (subscribeSceneClock) as a `transform` on each band wrapper
 * (never layout, never the path geometry), and only when the 0.1px-quantized
 * value changes. The easing is frame-rate independent (time constant
 * PARALLAX_EASE_MS), so it settles in the same wall time at 30 or 120 fps.
 *
 * Under reduced motion the Scene passes `frozen`: no listener, no
 * subscription, zero shift (a static composed frame).
 */

/** Time constant of the pointer easing, in ms. 200ms matches the old
 *  0.08-per-frame lerp at 60fps, now independent of the frame rate. */
const PARALLAX_EASE_MS = 200;

export interface PeaksProps {
  mood: SceneMood;
  /** When frozen (reduced-motion), parallax is disabled → static frame. */
  frozen?: boolean;
}

export function Peaks({ mood, frozen = false }: PeaksProps) {
  const bands = useRef<(HTMLDivElement | null)[]>([]);
  const bandRef = useCallback((i: number, el: HTMLDivElement | null) => {
    bands.current[i] = el;
  }, []);

  useEffect(() => {
    if (frozen || typeof window === "undefined") return;
    let target = 0;
    let current = 0;
    let lastT: number | null = null;
    const written: string[] = [];

    const onMove = (e: PointerEvent) => {
      target = (e.clientY / (window.innerHeight || 1)) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const unsubscribe = subscribeSceneClock((t) => {
      const dt = lastT == null ? 0 : t - lastT;
      lastT = t;
      current += (target - current) * (1 - Math.exp(-dt / PARALLAX_EASE_MS));
      const drift = sceneLayerTransform("peaks", t);
      PEAK_BANDS.forEach((band, i) => {
        const el = bands.current[i];
        if (!el) return;
        const next = peakBandTransform(peakBandShiftPx(band.depth, current, drift.y), drift.x);
        if (next === written[i]) return; // no style write when nothing moved
        written[i] = next;
        el.style.transform = next;
      });
    }, { reducedMotion: false });

    return () => {
      window.removeEventListener("pointermove", onMove);
      unsubscribe();
      for (const el of bands.current) if (el) el.style.transform = "";
    };
  }, [frozen]);

  return (
    <div className="absolute inset-0" data-testid="peaks-layer" aria-hidden="true">
      <ProceduralSky mood={mood} bandRef={bandRef} />
    </div>
  );
}

export default Peaks;
