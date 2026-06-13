/**
 * crossfadeMachine.ts — the interruptible two-slot crossfade state machine
 * (ALC SPR-06 M3).
 *
 * THE PROBLEM IT SOLVES (and why a state machine, not a key-remount):
 *
 * The SPR-04 crossfade keyed the incoming art on `fadeKey` and ran a CSS
 * keyframe animation from opacity 0. That is NOT interruptible: a `key` change
 * REMOUNTS the element, and a keyframe animation always restarts from its 0%
 * frame — so a mood flip MID-FADE throws away the in-progress element and starts
 * a fresh fade from black. From the current visual state at 50%, that reads as a
 * JUMP-CUT (snap to 0, re-run), exactly the discontinuity M3 forbids.
 *
 * THE FIX — two PERSISTENT slots (A / B) that never remount:
 *
 * We keep two layers alive for the whole scene lifetime. Each art swap assigns
 * the NEW art to whichever slot is currently the "back" slot and makes it the
 * "front": the front slot's opacity TARGET becomes the painted ceiling, the back
 * slot's target becomes 0. The DOM element is stable (we only change its
 * background-image + opacity target), so a CSS `transition: opacity` interpolates
 * from the element's CURRENT COMPUTED opacity to the new target. A second flip
 * mid-transition simply changes the targets again → the browser retargets from
 * where each slot IS — a smooth glide, never a restart-from-0.
 *
 * INTERRUPTION SEMANTICS (the invariant SPR-07/08 must not break):
 *   • RETARGET FROM CURRENT, never queue. There is no pending-swap queue. A new
 *     art always becomes the front immediately; the machine never holds a swap
 *     to "play after the current one finishes." Queuing would make a rapid burst
 *     of mood flips play as a stuttering sequence of full fades instead of a
 *     single smooth glide to the latest art. If someone adds a queue here, the
 *     interruption test (mid-flip retarget) breaks — that is the guard.
 *   • The machine is a PURE reducer over {slots, front}. It computes the next
 *     slot assignment + opacity targets from the previous state + the new art
 *     URL. No DOM, no time, no React — unit-testable in isolation (the M3
 *     "state-machine mid-flip" rigor item).
 *
 * It carries NO fetch logic: fetch non-amplification is already guaranteed
 * upstream (useKreaScene's reqId stale-discard + the [key] effect; useSceneArt's
 * mood-gated promote). This machine is purely the VISUAL crossfade choreography.
 */

/** The two persistent crossfade slots. */
export type SlotId = "A" | "B";

/** One slot's render state: which image it paints + its current opacity target. */
export interface SlotState {
  /** The image URL this slot paints, or null when the slot has never been used. */
  url: string | null;
  /** The opacity TARGET (the CSS transition eases toward this from current). */
  target: number;
}

export interface CrossfadeState {
  A: SlotState;
  B: SlotState;
  /** Which slot is currently the FRONT (fading toward painted). */
  front: SlotId;
}

/** The painted-opacity ceiling is injected (sourced from the CROSSFADE token)
 *  so this module owns no literal — the value's home is sceneMotion.ts. */
export interface CrossfadeReduceOpts {
  paintedOpacity: number;
}

/** The initial state: both slots empty, A nominally the front, nothing painted. */
export function initCrossfade(): CrossfadeState {
  return {
    A: { url: null, target: 0 },
    B: { url: null, target: 0 },
    front: "A",
  };
}

const other = (s: SlotId): SlotId => (s === "A" ? "B" : "A");

/**
 * Reduce: a NEW live art URL arrived (or art cleared to null on fallback).
 *
 * Cases:
 *   • url === current front url  → no-op (same art; do not re-trigger a fade).
 *   • url is a new live URL      → assign it to the BACK slot, flip front to it;
 *                                  new front target = painted, old front → 0.
 *   • url === null (fallback)    → both slots ease to 0 (the art releases; the
 *                                  procedural floor becomes the whole picture).
 *
 * INTERRUPTIBLE: because we only ever change `target` on PERSISTENT slots, a
 * caller that fires this mid-fade just moves the targets; the CSS transition
 * glides from current. We never reset a slot's element, never queue.
 */
export function crossfadeReduce(
  state: CrossfadeState,
  url: string | null,
  opts: CrossfadeReduceOpts,
): CrossfadeState {
  const painted = opts.paintedOpacity;
  const frontSlot = state[state.front];

  // Fallback / cleared art: release BOTH slots toward 0 (procedural-only).
  if (url == null) {
    // Already released? no-op (avoids a redundant state object).
    if (state.A.target === 0 && state.B.target === 0) return state;
    return {
      A: { ...state.A, target: 0 },
      B: { ...state.B, target: 0 },
      front: state.front,
    };
  }

  // Same art already on the front at full target → nothing to do.
  if (frontSlot.url === url && frontSlot.target === painted) {
    return state;
  }

  // A genuinely new art (or a re-show of art that had been released): put it on
  // the BACK slot and flip. The OLD front eases out; the NEW front eases in.
  const back = other(state.front);
  const next: CrossfadeState = {
    A: state.A,
    B: state.B,
    front: back,
  };
  next[back] = { url, target: painted };
  next[state.front] = { ...state[state.front], target: 0 };
  return next;
}
