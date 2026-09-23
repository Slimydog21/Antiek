import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";

/**
 * The scene heartbeat — the ONE requestAnimationFrame loop behind the living
 * mountainscape (SPR-04, milestones 1 + 6).
 *
 * A module singleton: every animated layer (Peaks parallax + drift, the Krea
 * art drift + crossfade, the Clouds and Snow canvases) subscribes here and
 * paints inside the same frame callback. However many layers subscribe, the
 * browser is asked for exactly one rAF per frame, and the per-frame work
 * writes the DOM or a canvas directly; nothing calls React setState per frame.
 * (Before 2026-09-23 the hook and each canvas ran their own loop, and the hook
 * re-rendered the Scene tree every tick: 3 loops and a React commit per frame.)
 *
 * THREE STATES, by design (the degradation ladder, rungs for milestone 6):
 *
 *   1. RUNNING   — at least one subscriber, tab visible: one rAF loop ticks,
 *                  `t` advances, `frame` increments.
 *   2. FROZEN    — reduced motion. A frozen subscriber gets ONE call at
 *                  FROZEN_T and is never registered, so it can never start
 *                  the loop: zero per-frame CPU, one deterministic frame.
 *   3. PAUSED    — the document is hidden. The loop is cancelled and `t`
 *                  holds; it resumes without a time jump when shown.
 *
 * Time is shared: a layer that re-subscribes (mood change) picks up the
 * running `t`, so drift never jumps back to zero mid-session. When the last
 * subscriber leaves, the heartbeat stops and resets, and the next subscriber
 * starts a fresh clock at frame 1.
 *
 * DETERMINISM: when frozen, `t === FROZEN_T` exactly, so a seeded layer
 * snapshots identically across runs (milestone 2 + 5 tests rely on this).
 */

/** The single composed-frame timestamp used in the reduced-motion freeze.
 *  A non-zero constant so layers that key motion off `t` show a settled,
 *  mid-cycle frame (not their t=0 start pose), but it is FIXED so the frame
 *  is deterministic. Chosen as 1500 ms ≈ a calm point a couple of seconds in. */
export const FROZEN_T = 1500;

/** Largest step one frame may advance `t`, so a long frame never lurches. */
const MAX_FRAME_MS = 64;

export type SceneFrameCallback = (t: number, frame: number) => void;

const subscribers = new Set<SceneFrameCallback>();
let rafId: number | null = null;
let lastTs: number | null = null;
let clockT = 0;
let frameN = 0;

function tick(ts: number): void {
  if (lastTs == null) lastTs = ts;
  clockT += Math.min(ts - lastTs, MAX_FRAME_MS);
  lastTs = ts;
  frameN += 1;
  rafId = requestAnimationFrame(tick);
  // Set iteration tolerates a subscriber leaving mid-frame (no allocation).
  for (const onFrame of subscribers) onFrame(clockT, frameN);
}

function start(): void {
  if (rafId != null || subscribers.size === 0) return;
  if (typeof document !== "undefined" && document.hidden) return;
  lastTs = null; // resume without a time jump
  rafId = requestAnimationFrame(tick);
}

function stop(): void {
  if (rafId != null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  lastTs = null;
}

function onVisibility(): void {
  if (document.hidden) stop();
  else start();
}

/** The heartbeat's current time in ms (0 before the first frame). Layers read
 *  it at render time to seed state that the next frame will continue. */
export function sceneClockNow(): number {
  return clockT;
}

/**
 * Subscribe a painter to the heartbeat. Returns a teardown.
 *
 * Under reduced motion (explicit, or the OS setting when not given) the
 * painter gets exactly one call at (FROZEN_T, 0) and is never registered, so
 * it can never start the loop. Without requestAnimationFrame (non-browser
 * tests) it likewise gets one static frame.
 */
export function subscribeSceneClock(
  onFrame: SceneFrameCallback,
  opts?: { reducedMotion?: boolean },
): () => void {
  const reducedMotion =
    opts?.reducedMotion ??
    (typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  if (reducedMotion || typeof requestAnimationFrame !== "function") {
    onFrame(FROZEN_T, 0);
    return () => {};
  }

  if (subscribers.size === 0) {
    clockT = 0;
    frameN = 0;
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }
  }
  subscribers.add(onFrame);
  start();

  let active = true;
  return () => {
    if (!active) return;
    active = false;
    subscribers.delete(onFrame);
    if (subscribers.size > 0) return;
    stop();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibility);
    }
  };
}

export interface SceneClockState {
  /** True when the scene composes one static frame (reduced motion). */
  frozen: boolean;
}

/**
 * The Scene's view of the heartbeat. It re-renders only when the motion
 * preference flips, never per frame: layers that move subscribe with
 * `subscribeSceneClock` and write the DOM themselves.
 */
export function useSceneClock(): SceneClockState {
  return { frozen: usePrefersReducedMotion() };
}
