import { useEffect, useRef, useState } from "react";

import type { SceneMood } from "../mood";
import { MAX_PARALLAX_PX, PEAK_BANDS } from "../peaks";
import { ProceduralSky } from "./ProceduralSky";

/**
 * Peaks (SPR-04, milestone 2 — subtle peak parallax).
 *
 * Renders the procedural sky+peaks (ProceduralSky owns the geometry) and adds
 * BOUNDED pointer/scroll parallax: as the pointer moves across the viewport,
 * the peak bands shift by a tiny amount, far bands less than near bands, giving
 * depth without nausea.
 *
 * ANTI-NAUSEA BOUND (acceptance criterion): the absolute shift is capped at
 * MAX_PARALLAX_PX (±8px) and scaled by each band's `depth`. Full pointer travel
 * across the whole viewport produces at most ±8px of near-band shift — read as
 * depth, never as disorienting motion. Under reduced-motion the Scene passes
 * `frozen`, and we render with ZERO shift (a static composed frame).
 */

export interface PeaksProps {
  mood: SceneMood;
  /** When frozen (reduced-motion), parallax is disabled → static frame. */
  frozen?: boolean;
}

/** Bounded pointer parallax: returns a normalized pointer offset in [-1,1] on
 *  each axis, smoothed. Listens at the window so the whole scene reacts. No-op
 *  (returns 0,0) when frozen or when there is no window. */
function usePointerParallax(frozen: boolean): { nx: number; ny: number } {
  const [p, setP] = useState({ nx: 0, ny: 0 });
  const raf = useRef<number | null>(null);
  const target = useRef({ nx: 0, ny: 0 });
  const cur = useRef({ nx: 0, ny: 0 });

  useEffect(() => {
    if (frozen || typeof window === "undefined") {
      setP({ nx: 0, ny: 0 });
      return;
    }
    const onMove = (e: PointerEvent) => {
      const w = window.innerWidth || 1;
      const h = window.innerHeight || 1;
      // Map to [-1,1], centered.
      target.current = {
        nx: (e.clientX / w) * 2 - 1,
        ny: (e.clientY / h) * 2 - 1,
      };
      if (raf.current == null) raf.current = requestAnimationFrame(ease);
    };
    const ease = () => {
      // Critically-damped-ish lerp toward the target so the parallax glides
      // (no jitter), and SETTLES (stops the loop) once close enough — so we
      // don't burn a permanent rAF just for parallax.
      cur.current = {
        nx: cur.current.nx + (target.current.nx - cur.current.nx) * 0.08,
        ny: cur.current.ny + (target.current.ny - cur.current.ny) * 0.08,
      };
      setP({ nx: cur.current.nx, ny: cur.current.ny });
      const settled =
        Math.abs(target.current.nx - cur.current.nx) < 0.001 &&
        Math.abs(target.current.ny - cur.current.ny) < 0.001;
      raf.current = settled ? null : requestAnimationFrame(ease);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (raf.current != null) cancelAnimationFrame(raf.current);
      raf.current = null;
    };
  }, [frozen]);

  return p;
}

export function Peaks({ mood, frozen = false }: PeaksProps) {
  const { ny } = usePointerParallax(frozen);
  // Per-band vertical shift: depth × cap × pointer-y. Bounded by construction.
  const shifts = PEAK_BANDS.map((b) => b.depth * MAX_PARALLAX_PX * ny);
  return (
    <div className="absolute inset-0" data-testid="peaks-layer" aria-hidden="true">
      <ProceduralSky mood={mood} shifts={shifts} />
    </div>
  );
}

export default Peaks;
