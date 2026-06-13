import { useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";

/**
 * useSceneClock — the single requestAnimationFrame heartbeat for the living
 * mountainscape (SPR-04 milestones 1 + 6; SPR-06 M1 adds the deterministic
 * time seam + the continuous phase scalar).
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
 *
 * ─── SPR-06 M1: the two new outputs (both ADDITIVE — `t`/`frame` unchanged) ──
 *
 *   (a) An INJECTABLE TIME SOURCE (`getTime`). Production reads the wall clock
 *       (`() => Date.now()`); tests and SPR-05's deterministic snapshots inject
 *       a FIXED source so the SCENE STATE is byte-identical across runs. The
 *       time source feeds ONLY the new `phase` scalar (light drift) — it does
 *       NOT touch `t`/`frame` (the rAF-elapsed counters the canvas painters
 *       ride), so the cadence invariant and the painter behaviour are untouched.
 *
 *   (b) A CONTINUOUS 0..1 PHASE SCALAR (`phase`). Today's discrete mood snaps
 *       (light → day, dark → night). `phase` is the SMOOTH time-of-day position
 *       so procedural light can DRIFT through dawn/dusk instead of snapping —
 *       it is the seam SPR-06's drift/crossfade choreography eases against. The
 *       DISCRETE mood/state output that useSceneArt watches is DERIVED ELSEWHERE
 *       (mood.ts) and is NOT affected by `phase`: the fetch cadence stays
 *       mood-gated (phase changing every frame must NEVER trigger a fetch).
 *
 * THE CADENCE INVARIANT, named once more (SPR-06): `phase` updates continuously
 * while running, but it is NOT a dependency of useSceneArt and is NOT derived
 * into the mood — so no amount of phase drift can amplify Krea fetches. The
 * 120-render/1-fetch test (useSceneArt.test.tsx) + the N-flips test stay green.
 */

/** The single composed-frame timestamp used in the reduced-motion freeze.
 *  A non-zero constant so layers that key motion off `t` show a settled,
 *  mid-cycle frame (not their t=0 start pose), but it is FIXED so the frame
 *  is deterministic. Chosen as 1500 ms ≈ a calm point a couple of seconds in. */
export const FROZEN_T = 1500;

/** The wall-clock time source used in production: the current epoch ms. Tests
 *  and SPR-05's deterministic snapshots inject a FIXED replacement so the phase
 *  scalar (and therefore the whole composed scene) is byte-identical per run. */
export type TimeSource = () => number;

/** The default production time source. Isolated so the injection seam has a
 *  single, named default and tests can assert "no injection ⇒ wall clock". */
export const wallClock: TimeSource = () => Date.now();

/** Milliseconds in a day — the period the phase scalar wraps over. */
const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * The continuous 0..1 time-of-day phase from an epoch-ms instant, in LOCAL
 * time (the scene's light should track the viewer's local day, the same local
 * frame the OS `prefers-color-scheme` mood already follows).
 *
 *   phase = 0.0  ⇔ local midnight (00:00)
 *   phase = 0.25 ⇔ 06:00 (dawn)
 *   phase = 0.5  ⇔ 12:00 (noon)
 *   phase = 0.75 ⇔ 18:00 (dusk)
 *
 * CONTINUOUS + MONOTONIC WITHIN A DAY, WRAPPING at the day boundary: as wall
 * time advances from 23:59 to 00:00 the phase wraps 0.999… → 0.0 (a clean
 * single-cycle wrap, never a backwards jump within the cycle). Pure + exported
 * so the boundary unit tests (23:59→00:00, the dawn/dusk edges) assert it
 * directly without a clock loop.
 */
export function phaseOf(epochMs: number): number {
  const d = new Date(epochMs);
  const localMs =
    d.getHours() * 3_600_000 +
    d.getMinutes() * 60_000 +
    d.getSeconds() * 1000 +
    d.getMilliseconds();
  // localMs ∈ [0, DAY_MS); divide for [0,1). The modulo guards a leap-second /
  // DST edge from ever pushing the value to exactly 1.0 (which would read as a
  // discontinuous "next day start" within the same cycle).
  return (localMs % DAY_MS) / DAY_MS;
}

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
  /** SPR-06 M1 — continuous 0..1 time-of-day position (see phaseOf). The seam
   *  procedural light drifts against; NOT involved in the discrete mood or the
   *  Krea fetch cadence. Sampled from the injected time source each running
   *  tick; held at its mount value while frozen (a fixed, deterministic phase
   *  — the static composition's designed light). */
  phase: number;
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
 *
 * @param getTime  injectable time source for the phase scalar. Production omits
 *                 it (defaults to the wall clock); tests + SPR-05 snapshots
 *                 inject a FIXED source for byte-identical scene state.
 */
export function useSceneClock(getTime: TimeSource = wallClock): SceneClock {
  const reducedMotion = usePrefersReducedMotion();

  const [clock, setClock] = useState<SceneClock>(() => ({
    t: reducedMotion ? FROZEN_T : 0,
    frame: 0,
    running: false,
    frozen: reducedMotion,
    phase: phaseOf(getTime()),
  }));

  // Mutable accumulators so the rAF callback never closes over stale state.
  const tRef = useRef(reducedMotion ? FROZEN_T : 0);
  const frameRef = useRef(0);
  const lastTsRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  // Keep the latest getTime in a ref so the rAF loop reads the CURRENT injected
  // source without re-subscribing the effect every render (the effect depends
  // only on reducedMotion — re-subscribing per render would churn rAF).
  const getTimeRef = useRef(getTime);
  getTimeRef.current = getTime;

  useEffect(() => {
    // RUNG 2 — reduced-motion: never schedule a loop; emit one frozen frame.
    // Phase holds at a single sampled value (deterministic under an injected
    // fixed source) — the static composition's designed light, no drift.
    if (reducedMotion) {
      tRef.current = FROZEN_T;
      frameRef.current = 0;
      lastTsRef.current = null;
      setClock({
        t: FROZEN_T,
        frame: 0,
        running: false,
        frozen: true,
        phase: phaseOf(getTimeRef.current()),
      });
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
        // Sample the (live) time source each tick → continuous light drift.
        phase: phaseOf(getTimeRef.current()),
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
 *
 * SPR-06 M1: `onFrame` now receives the continuous `phase` as a third arg, so a
 * canvas painter that wants to tint with the time-of-day light reads it WITHOUT
 * a React re-render (the same off-reconciler path `t`/`frame` already use). The
 * `getTime` source is injectable here too, defaulting to the wall clock — under
 * reduced-motion it is sampled exactly ONCE (the one frozen frame), never looped.
 */
export function subscribeSceneClock(
  onFrame: (t: number, frame: number, phase: number) => void,
  opts?: { reducedMotion?: boolean; getTime?: TimeSource },
): () => void {
  const reducedMotion =
    opts?.reducedMotion ??
    (typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const getTime = opts?.getTime ?? wallClock;

  if (reducedMotion) {
    // One static composed frame; no loop ever scheduled. Phase sampled once.
    onFrame(FROZEN_T, 0, phaseOf(getTime()));
    return () => {};
  }

  if (typeof requestAnimationFrame !== "function") {
    // Non-browser / test env without rAF: emit one frame, no loop.
    onFrame(FROZEN_T, 0, phaseOf(getTime()));
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
    onFrame(t, frame, phaseOf(getTime()));
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
