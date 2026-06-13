import { useEffect, useRef, useState } from "react";

import { subscribeSceneClock, type TimeSource } from "./useSceneClock";
import { DRIFT } from "../design/motion/sceneMotion";
import type { PlaneSeam } from "./layers/Mountainscape";

/**
 * useSceneDrift — the parallax BREATH (ALC SPR-06 M4).
 *
 * Drives the far/mid/near depth planes of SPR-05's Mountainscape with a slow,
 * subtle, INDEPENDENT drift — the scene "breathing." It consumes SPR-05's seams
 * THROUGH THE INTERFACE ONLY: it produces an array of `PlaneSeam` (transform +
 * optional opacity) that Scene passes to `<Mountainscape seams={…}/>`. It NEVER
 * edits Mountainscape's internals (the diff-scope check) — SPR-05 owns the layer;
 * SPR-06 only fills the typed seam SPR-05 deliberately exposed.
 *
 * THE BREATH (every parameter is a token in sceneMotion.ts, with rationale):
 *   • Each plane oscillates on its OWN period (DRIFT.periodsMs / periodsYMs),
 *     and the periods are mutually PRIME so the planes never re-align — the
 *     composition never visibly loops (proven in sceneMotion.test.ts).
 *   • Amplitude scales by the plane's parallax DEPTH (far breathes least, near
 *     most), capped at DRIFT.maxAmplitudePx (horizontal) / maxAmplitudeYPx
 *     (vertical, subtler). The cap is BELOW the interactive pointer parallax
 *     (peaks.ts ±8px) so the ambient breath never out-shouts a deliberate move.
 *   • Transform ONLY (translate). No layout props, no opacity churn → GPU-cheap,
 *     never thrashes layout, never trips the motion guard.
 *
 * DETERMINISTIC: the drift is a PURE function of elapsed clock time `t` and the
 * plane depths (driftSeams below). Under the FIXED clock (injected getTime) the
 * seams are byte-stable across runs — SPR-05's snapshot harness can render a
 * drifting composition reproducibly.
 *
 * REDUCED MOTION (M5): when frozen, every amplitude collapses to
 * DRIFT.reducedAmplitudePx (0) → the planes sit at their designed STATIC pose
 * (the SPR-05 composition IS the reduced state). We also never subscribe a loop
 * when reduced (subscribeSceneClock emits one frozen frame), so there is zero
 * per-frame work — the same structural freeze the rest of the scene uses.
 *
 * CADENCE: the drift rides the EXISTING scene clock (one rAF loop, many
 * consumers). It schedules NO new loop and triggers NO fetch — the fetch cadence
 * is mood-gated and entirely untouched by drift.
 */

/**
 * PURE: the per-plane drift seams at elapsed time `t` (ms), for the given plane
 * depths. Exported as the unit-test + determinism seam.
 *
 * Each plane p gets:
 *   dx = depth_p · maxAmplitudePx  · sin(2π · t / periodMs_p)
 *   dy = depth_p · maxAmplitudeYPx · sin(2π · t / periodYMs_p)
 * a slow Lissajous breath (x and y on distinct prime periods → never a straight
 * diagonal, never a repeating loop). Translate-only transform.
 *
 * @param t             elapsed clock time in ms (from useSceneClock).
 * @param depths        per-plane parallax depth (Mountainscape PLANE_DEPTHS).
 * @param reducedMotion when true, every seam is the identity (no transform) —
 *                      the static designed pose.
 */
export function driftSeams(
  t: number,
  depths: readonly number[],
  reducedMotion = false,
): PlaneSeam[] {
  if (reducedMotion) {
    // The breath stops: identity seams → the planes render at their static pose.
    return depths.map(() => ({}));
  }
  const ampX = DRIFT.maxAmplitudePx;
  const ampY = DRIFT.maxAmplitudeYPx;
  return depths.map((depth, i) => {
    // Each plane reads its own prime period; if there are more planes than
    // periods (shouldn't happen — sceneMotion asserts 3), wrap defensively.
    const px = DRIFT.periodsMs[i % DRIFT.periodsMs.length];
    const py = DRIFT.periodsYMs[i % DRIFT.periodsYMs.length];
    const dx = depth * ampX * Math.sin((2 * Math.PI * t) / px);
    const dy = depth * ampY * Math.sin((2 * Math.PI * t) / py);
    // Round to 3dp so the transform string is byte-stable (determinism gate)
    // and the DOM doesn't churn on sub-pixel noise.
    const rx = Math.round(dx * 1000) / 1000;
    const ry = Math.round(dy * 1000) / 1000;
    return { transform: `translate(${rx}px, ${ry}px)` };
  });
}

/**
 * The React hook: subscribe to the scene clock and emit the current per-plane
 * drift seams. Re-renders the (cheap) Scene wrapper per tick — but ONLY the
 * Mountainscape's plane `<g>` transforms change (transform-only, compositor-
 * cheap); the heavy canvas painters ride their own off-reconciler subscription.
 *
 * @param depths   the plane depths to drive (Mountainscape PLANE_DEPTHS).
 * @param frozen   reduced-motion: emit static identity seams, no loop.
 * @param getTime  injectable time source (tests / determinism); the breath
 *                 itself is driven by the clock's ELAPSED t, not wall time, so
 *                 getTime only matters for the clock's phase — passed through for
 *                 a single, consistent clock seam.
 */
export function useSceneDrift(
  depths: readonly number[],
  frozen: boolean,
  getTime?: TimeSource,
): PlaneSeam[] {
  const [seams, setSeams] = useState<PlaneSeam[]>(() =>
    driftSeams(0, depths, frozen),
  );
  // Keep depths in a ref so the subscription effect depends only on frozen —
  // the depths array is a stable module constant in practice (PLANE_DEPTHS).
  const depthsRef = useRef(depths);
  depthsRef.current = depths;

  useEffect(() => {
    if (frozen) {
      // Static designed pose; no loop. One identity emission.
      setSeams(driftSeams(0, depthsRef.current, true));
      return;
    }
    const stop = subscribeSceneClock(
      (t) => setSeams(driftSeams(t, depthsRef.current, false)),
      { reducedMotion: false, getTime },
    );
    return stop;
    // getTime is intentionally not a dep: it is read fresh inside subscribe; a
    // changing getTime identity must not re-subscribe the loop (cadence).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frozen]);

  return seams;
}
