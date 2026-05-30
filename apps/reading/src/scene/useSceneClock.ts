import { useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";

/**
 * useSceneClock — the single requestAnimationFrame heartbeat for the living
 * mountainscape (SPR-04, milestones 1 + 6).
 *
 * It is the ONLY rAF loop in the scene: every animated layer (Clouds, Snow,
 * Peaks parallax) reads the clock's `t` (elapsed ms) rather than scheduling
 * its own loop. One loop, many consumers — so there is exactly one place to
 * freeze, pause, and budget.
 *
 * THREE STATES, by design (the degradation ladder, rungs for milestone 6):
 *
 *   1. RUNNING   — a real rAF loop ticks; `t` advances; `frame` increments.
 *   2. FROZEN    — `prefers-reduced-motion: reduce`. NO rAF loop is ever
 *                  scheduled (we never call requestAnimationFrame). `t` is a
 *                  single fixed value (FROZEN_T) so every layer composes ONE
 *                  static, deterministic frame. This is not "pause": the loop
 *                  is never created, so there is zero per-frame CPU.
 *   3. PAUSED    — the document is hidden (`visibilitychange`). The loop is
 *                  torn down (cancelAnimationFrame) and `t` holds its last
 *                  value; it resumes — without a time jump — when the tab is
 *                  shown again. Saves CPU and, transitively, Krea cost (no
 *                  mood re-evaluation churn while nobody is looking).
 *
 * DETERMINISM: when frozen, `t === FROZEN_T` exactly, so a seeded layer
 * snapshots identically across runs (milestone 2 + 5 tests rely on this).
 */

/** The single composed-frame timestamp used in the reduced-motion freeze.
 *  A non-zero constant so layers that key motion off `t` show a settled,
 *  mid-cycle frame (not their t=0 start pose), but it is FIXED so the frame
 *  is deterministic. Chosen as 1500 ms ≈ a calm point a couple of seconds in. */
export const FROZEN_T = 1500;

export interface SceneClock {
  /** Elapsed animation time in ms (drift-free: accumulates only while
   *  running, excludes hidden-tab gaps). FROZEN_T when reduced-motion. */
  t: number;
  /** Monotonic frame counter while running; 0 when frozen. Tests assert
   *  "same seed → same frame N" against this. */
  frame: number;
  /** True while a real rAF loop is ticking (running, visible, not reduced). */
  running: boolean;
  /** True when frozen to a single static frame (reduced-motion). */
  frozen: boolean;
}

/**
 * Subscribe to the scene clock. Returns the live clock state. Re-renders the
 * caller each tick while running; renders ONCE (no further re-renders) while
 * frozen or paused.
 *
 * Note for perf: a per-tick React re-render of the whole Scene tree would be
 * wasteful. In practice each canvas layer subscribes via a ref (see the
 * `subscribe` form below) so the heavy painters read `t` inside their own rAF
 * callback without forcing React reconciliation. This hook's state is used for
 * the lightweight "running/frozen" decisions and crossfade timing.
 */
export function useSceneClock(): SceneClock {
  const reducedMotion = usePrefersReducedMotion();

  const [clock, setClock] = useState<SceneClock>(() => ({
    t: reducedMotion ? FROZEN_T : 0,
    frame: 0,
    running: false,
    frozen: reducedMotion,
  }));

  // Mutable accumulators so the rAF callback never closes over stale state.
  const tRef = useRef(reducedMotion ? FROZEN_T : 0);
  const frameRef = useRef(0);
  const lastTsRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    // RUNG 2 — reduced-motion: never schedule a loop; emit one frozen frame.
    if (reducedMotion) {
      tRef.current = FROZEN_T;
      frameRef.current = 0;
      lastTsRef.current = null;
      setClock({ t: FROZEN_T, frame: 0, running: false, frozen: true });
      return; // no rAF, no listener — zero per-frame work.
    }

    const tick = (ts: number) => {
      if (lastTsRef.current == null) lastTsRef.current = ts;
      const dt = ts - lastTsRef.current;
      lastTsRef.current = ts;
      // Guard against a huge dt after a resume (we tear down on hide, so this
      // is belt-and-braces): clamp a single frame to <= ~64ms so the scene
      // never lurches.
      tRef.current += Math.min(dt, 64);
      frameRef.current += 1;
      setClock({
        t: tRef.current,
        frame: frameRef.current,
        running: true,
        frozen: false,
      });
      rafRef.current = requestAnimationFrame(tick);
    };

    const start = () => {
      if (rafRef.current != null) return; // already running
      lastTsRef.current = null; // resume without a time jump
      rafRef.current = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastTsRef.current = null;
    };

    // RUNG 3 — visibility: pause the loop while hidden, resume on show.
    const onVisibility = () => {
      if (typeof document === "undefined") return;
      if (document.hidden) {
        stop();
        // Mark not-running so consumers can show a settled frame; `t` holds.
        setClock((c) => ({ ...c, running: false }));
      } else {
        start();
      }
    };

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }

    // RUNG 1 — start running (unless we mount already hidden).
    if (typeof document === "undefined" || !document.hidden) {
      start();
    }

    return () => {
      stop();
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
      }
    };
  }, [reducedMotion]);

  return clock;
}

/**
 * Imperative subscription form — for the heavy canvas painters that want to
 * read `t` inside their OWN rAF callback WITHOUT forcing a React re-render per
 * frame. Returns a teardown. Honours the same three states: it never starts a
 * loop under reduced-motion (it calls `onFrame(FROZEN_T, 0)` exactly once),
 * and it pauses on `visibilitychange`.
 *
 * This keeps the per-frame work off the React reconciler entirely — the
 * canvas mutates its own bitmap; React only ever sees mount/unmount.
 */
export function subscribeSceneClock(
  onFrame: (t: number, frame: number) => void,
  opts?: { reducedMotion?: boolean },
): () => void {
  const reducedMotion =
    opts?.reducedMotion ??
    (typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  if (reducedMotion) {
    // One static composed frame; no loop ever scheduled.
    onFrame(FROZEN_T, 0);
    return () => {};
  }

  if (typeof requestAnimationFrame !== "function") {
    // Non-browser / test env without rAF: emit one frame, no loop.
    onFrame(FROZEN_T, 0);
    return () => {};
  }

  let t = 0;
  let frame = 0;
  let last: number | null = null;
  let raf: number | null = null;

  const tick = (ts: number) => {
    if (last == null) last = ts;
    t += Math.min(ts - last, 64);
    last = ts;
    frame += 1;
    onFrame(t, frame);
    raf = requestAnimationFrame(tick);
  };
  const start = () => {
    if (raf != null) return;
    last = null;
    raf = requestAnimationFrame(tick);
  };
  const stop = () => {
    if (raf != null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
    last = null;
  };

  const onVisibility = () => {
    if (typeof document === "undefined") return;
    if (document.hidden) stop();
    else start();
  };
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisibility);
  }
  if (typeof document === "undefined" || !document.hidden) start();

  return () => {
    stop();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibility);
    }
  };
}
