import { useEffect, useRef } from "react";

/**
 * useMouseFollow (SPR-05) — the ~0.5-second-LAGGED cursor pursuit.
 *
 * It is a SAMPLE-DELAY pursuit, not an ease-time-constant chase. We record
 * the pointer into a small ring buffer stamped with the (fake-clock-aware)
 * time of each sample. The follow TARGET is the pointer position from
 * ~LAG_MS ago — literally "where the mouse was 0.5 seconds back" — and Werner
 * eases toward THAT. So he trails the cursor by a real half-second rather
 * than rubber-banding toward the live cursor with a 0.5s response curve.
 * The two feel different: the ease-constant version always snaps toward you;
 * this version is genuinely behind, which reads as a lively, attentive
 * companion rather than a cursor-locked reticle.
 *
 * It is honestly an APPROXIMATION of "0.5 seconds": the lag is exactly LAG_MS
 * only while the buffer spans that window. Right after mount (buffer not yet
 * deep enough) the oldest sample we have is younger than 0.5s, so the
 * effective lag ramps from ~0 up to LAG_MS over the first half-second. We
 * accept that — a cold start that snaps to a true 0.5s-old point would
 * require inventing history. After the ramp it is a faithful 0.5s
 * sample-delay.
 *
 * This hook does NOT move anything. It is a pure read seam: it exposes, via a
 * ref the caller polls (no re-render per pointer move — that would thrash the
 * whole shell), the lagged target the mascot's roam should bias toward, plus
 * whether the pointer has gone idle. The mascot's existing chained-timeout
 * roam reads `read()` at the top of each leg.
 *
 * Reduced motion: the hook installs NO listeners and `read()` returns a
 * frozen `{ target: null }`, so the caller falls back to its own bounded
 * wander and there is zero involuntary cursor pursuit. Same when the tab is
 * hidden (we stop sampling on visibilitychange) — no work between wakeups.
 */

/** ~0.5 seconds. A snappy, responsive follow that reads as a lively companion
 *  rather than a sleepy one. The ring buffer holds ~500ms of 120ms samples. */
export const LAG_MS = 500;

/**
 * How often we snapshot the pointer into the ring. 120ms ≈ 8 samples/sec —
 * fine enough that the 0.5s-old point is well-resolved, coarse enough that the
 * buffer stays tiny and we don't do per-mousemove work. We sample on a timer,
 * not on every `mousemove`, so a frantic mouse can't flood the buffer.
 */
export const SAMPLE_INTERVAL_MS = 120;

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
  /** True when the pointer has been still for >= POINTER_IDLE_MS — the
   *  caller should wander rather than follow. */
  pointerIdle: boolean;
  /** The recommended ease factor for closing the gap toward `target`. */
  ease: number;
}

const FROZEN_READING: FollowReading = {
  target: null,
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
      if (count.current === 0) return { target: null, pointerIdle: true, ease: FOLLOW_EASE };

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
      if (!point) return { target: null, pointerIdle: true, ease: FOLLOW_EASE };

      const last = lastMove.current;
      const pointerIdle = last ? now - last.t >= POINTER_IDLE_MS : true;
      return { target: { x: point.x, y: point.y }, pointerIdle, ease: FOLLOW_EASE };
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
      // Pause sampling when the tab is hidden — no background work, and on
      // return we don't backfill a bogus straight-line jump.
      if (document.hidden) stopSampling();
      else startSampling();
    };

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
