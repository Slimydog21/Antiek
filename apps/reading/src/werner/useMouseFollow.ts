import { useEffect, useRef } from "react";

/**
 * useMouseFollow (SPR-05 / WERNER-ICE) — the pointer read seam (live + idle).
 *
 * ── FIXED-STATION MODEL (2026-07-02) ────────────────────────────────────────
 * Werner no longer CHASES the cursor — the reel that consumed this hook's lagged
 * `target` was removed (docs/htmlspec/werner-fixed-station/DESIGN.md). What the
 * station uses from this hook is the LIVE read:
 *   - `live`       — the exact live pointer position → the bait worm rides it
 *                    (the cursor IS the bait) and the fishing line's free end
 *                    lands there (the removed cursor-bait; the seam now feeds idle edges).
 *   - `pointerIdle`— has the pointer been still ≥ POINTER_IDLE_MS? This gates the
 *                    own-hole never-catch gag (idle) vs. the line-to-cursor
 *                    (active) — the station's one XOR.
 *   - `tabHidden`  — the bait + line hide when the tab is hidden.
 * The lagged `target` (+ `ease`, `centerLaggedTarget`, LAG_MS) and the ring
 * buffer below are RETAINED but currently dormant — the reel was their only
 * consumer. They are kept intact (and tested) rather than ripped out mid-rework:
 * trimming this shared hook to live-only is a separate, focused cleanup, because
 * the bait + line depend on the SAME sampling loop for `live`/`pointerIdle`.
 *
 * Sample-delay lag (dormant): the pointer is recorded into a small ring buffer
 * stamped with the (fake-clock-aware) time of each sample; the lagged `target`
 * is the pointer position from ~LAG_MS ago. It ramps from ~0 to LAG_MS over the
 * first half-second (a cold start can't invent history). No current consumer.
 *
 * Tab-return: sampling pauses while hidden (visibilitychange below) and we never
 * backfill a straight-line jump, so `live`/`target` pick up where they left off.
 *
 * This hook does NOT move anything. It is a pure read seam: it exposes, via a
 * ref the caller polls (no re-render per pointer move — that would thrash the
 * whole shell), the live/idle pointer read the bait, the line, and the station
 * gag consume.
 *
 * Reduced motion: the hook installs NO listeners and `read()` returns a frozen
 * `{ live: null, target: null }`, so there is zero involuntary behaviour. Same
 * when the tab is hidden — no work between wakeups.
 */

/** ~0.5 seconds sample-delay for the lagged hook (WERNER-ICE lag budget). */
export const LAG_MS = 500;

/**
 * Pointer ring sampling interval. 60ms ≈ 16.7 samples/sec inside a 500ms window
 * (WERNER-ICE SPR-13) — halves quantization error vs 120ms at the same LAG_MS.
 */
export const SAMPLE_INTERVAL_MS = 60;

/**
 * Lazy ease toward the lagged point, applied by the CALLER per roam leg. A
 * high factor (0..1) closes most of the gap per leg, keeping the penguin
 * close on the cursor's heels. At 0.75 and a 0.5s lag, Werner reads as a
 * lively, attentive companion — responsive but still with visible character.
 */
export const FOLLOW_EASE = 0.75;

/**
 * After this long with no pointer movement Werner is considered "idle on the
 * cursor" — the caller should switch from biased-follow to its own bounded
 * wander (so he doesn't freeze staring at a parked cursor). Distinct from the
 * follow path; resumes the moment the pointer moves again.
 */
export const POINTER_IDLE_MS = 2000;

/** Buffer depth: enough samples to span LAG_MS plus headroom. */
const RING_CAPACITY = Math.ceil(LAG_MS / SAMPLE_INTERVAL_MS) + 8;

interface Sample {
  x: number;
  y: number;
  t: number;
}

export interface FollowReading {
  /** Where the mouse was ~LAG_MS ago, or null if we can't/shouldn't follow
   *  (reduced motion, no samples yet, or the pointer never entered). */
  target: { x: number; y: number } | null;
  /** Live pointer (client coords). Null when disabled or no move yet. */
  live: { x: number; y: number } | null;
  /** True when the document is hidden — bait/line should hide. */
  tabHidden: boolean;
  /** True when the pointer has been still for >= POINTER_IDLE_MS — the
   *  caller should wander rather than follow. */
  pointerIdle: boolean;
  /** The recommended ease factor for closing the gap toward `target`. */
  ease: number;
}

/** Mascot top-left from a lagged client point (hook centering). */
export function centerLaggedTarget(
  lagged: { x: number; y: number } | null,
  mascotSize: number,
): { x: number; y: number } | null {
  if (!lagged) return null;
  const half = mascotSize / 2;
  return { x: lagged.x - half, y: lagged.y - half };
}

const FROZEN_READING: FollowReading = {
  target: null,
  live: null,
  tabHidden: true,
  pointerIdle: true,
  ease: FOLLOW_EASE,
};

export interface UseMouseFollowOptions {
  /** Freeze the hook entirely (reduced motion). Default false. */
  disabled?: boolean;
  /** Injectable clock for deterministic tests (defaults to performance.now /
   *  Date.now). Must be the SAME clock the test's fake timers advance. */
  now?: () => number;
}

export interface MouseFollow {
  /** Poll the current lagged target. Cheap; safe to call every roam leg. */
  read: () => FollowReading;
}

/**
 * Subscribe to the pointer and expose the lagged target via a polled ref.
 * Returns a stable object whose `read()` the caller invokes on demand.
 */
export function useMouseFollow(
  options: UseMouseFollowOptions = {},
): MouseFollow {
  const { disabled = false } = options;

  // The ring buffer + book-keeping live in refs so sampling never re-renders.
  const ring = useRef<Sample[]>([]);
  const head = useRef(0); // next write index (wraps)
  const count = useRef(0); // number of valid samples
  const lastMove = useRef<{ x: number; y: number; t: number } | null>(null);
  const tabHiddenRef = useRef(false);

  // A stable `now` for the lifetime of the hook (tests inject a fake clock).
  const nowRef = useRef<() => number>(
    options.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now())),
  );
  nowRef.current =
    options.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));

  // Keep a live `disabled` flag the reader can see without re-creating it.
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;

  // The reader is a stable identity so the mascot effect doesn't re-run when
  // this hook re-renders. It closes over the refs, which always hold live data.
  const reader = useRef<MouseFollow>({
    read: (): FollowReading => {
      if (disabledRef.current) return FROZEN_READING;
      const buf = ring.current;
      if (count.current === 0) {
        // No ring samples yet (before the first sampler tick). `live` + idleness
        // still come from lastMove, so a pointer that JUST moved reads as active
        // even in this pre-sample window — otherwise the fishing line to the
        // cursor-bait would be suppressed for up to one SAMPLE_INTERVAL_MS after
        // the very first move on the page. Idle only if truly no recent move.
        const last = lastMove.current;
        const live = last ? { x: last.x, y: last.y } : null;
        const pointerIdle = last
          ? nowRef.current() - last.t >= POINTER_IDLE_MS
          : true;
        return {
          target: null,
          live,
          tabHidden: tabHiddenRef.current,
          pointerIdle,
          ease: FOLLOW_EASE,
        };
      }

      const now = nowRef.current();
      const cutoff = now - LAG_MS;
      // Walk the ring oldest→newest and take the newest sample at or before
      // the cutoff (the "where the mouse was 0.5s ago" point). If every sample
      // is younger than the cutoff (cold start, < 0.5s of history), fall back to
      // the OLDEST sample we have — the effective lag ramps up to LAG_MS.
      const cap = buf.length;
      const start = (head.current - count.current + cap) % cap;
      let chosen: Sample | null = null;
      let oldest: Sample | null = null;
      for (let i = 0; i < count.current; i++) {
        const s = buf[(start + i) % cap];
        if (oldest === null) oldest = s;
        if (s.t <= cutoff) chosen = s; // keep advancing → newest ≤ cutoff
      }
      const point = chosen ?? oldest;
      if (!point) {
        const live = lastMove.current
          ? { x: lastMove.current.x, y: lastMove.current.y }
          : null;
        return {
          target: null,
          live,
          tabHidden: tabHiddenRef.current,
          pointerIdle: true,
          ease: FOLLOW_EASE,
        };
      }

      const last = lastMove.current;
      const pointerIdle = last ? now - last.t >= POINTER_IDLE_MS : true;
      const live = last ? { x: last.x, y: last.y } : null;
      return {
        target: { x: point.x, y: point.y },
        live,
        tabHidden: tabHiddenRef.current,
        pointerIdle,
        ease: FOLLOW_EASE,
      };
    },
  });

  useEffect(() => {
    if (disabled || typeof window === "undefined") {
      // Reduced motion (or SSR): clear any history so a later enable starts
      // clean, and install nothing. No listeners, no timer → no work.
      ring.current = [];
      head.current = 0;
      count.current = 0;
      lastMove.current = null;
      return;
    }

    const onPointerMove = (e: PointerEvent | MouseEvent) => {
      lastMove.current = { x: e.clientX, y: e.clientY, t: nowRef.current() };
    };

    let sampler: number | null = null;

    const push = (s: Sample) => {
      const buf = ring.current;
      buf[head.current] = s;
      head.current = (head.current + 1) % RING_CAPACITY;
      if (count.current < RING_CAPACITY) count.current += 1;
    };

    const tick = () => {
      // Snapshot the last known pointer position on each interval. We resample
      // the held position even when the mouse is still so the ring keeps a
      // dense, evenly-spaced history (the 0.5s-old lookup stays well-resolved).
      const last = lastMove.current;
      if (last) push({ x: last.x, y: last.y, t: nowRef.current() });
    };

    const startSampling = () => {
      if (sampler !== null) return;
      sampler = window.setInterval(tick, SAMPLE_INTERVAL_MS);
    };
    const stopSampling = () => {
      if (sampler !== null) {
        window.clearInterval(sampler);
        sampler = null;
      }
    };

    const onVisibility = () => {
      tabHiddenRef.current = document.hidden;
      // Pause sampling when the tab is hidden — no background work, and on
      // return we don't backfill a bogus straight-line jump.
      if (document.hidden) stopSampling();
      else startSampling();
    };
    tabHiddenRef.current = document.hidden;

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) startSampling();

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("visibilitychange", onVisibility);
      stopSampling();
    };
  }, [disabled]);

  return reader.current;
}
