import {
  INITIAL_WERNER_STATE,
  isBusy,
  wernerReducer,
  type WernerState,
} from "./wernerState";
import { emoteDurationMs, type EmoteKind } from "./emotes";

/**
 * WernerStage (SPR-05) — the imperative command controller.
 *
 * This is the SPR-10 seam: a small object exposing moveTo / waddleToEl /
 * emote / follow / idle / freeze. It owns the STATE MACHINE (wernerState.ts)
 * and the directed-action timers, but it does NOT own a second position. It
 * drives the mascot's EXISTING `pos` ref + chained-timeout roam through a
 * thin adapter the mascot passes in (`StageHost`). One penguin, one position.
 *
 * Why an injected host rather than reaching into the DOM: the mascot already
 * owns clampRectToViewport, applyPos, the bob-class swap, and the roam re-arm.
 * Re-implementing any of that here would fork the position source — the exact
 * thing the task forbids. So the stage asks the host to "walk Werner to (x,y)
 * with the gait on" and the host reuses its own machinery. The stage's job is
 * sequencing (waddle → emote → idle) and the latest-wins cancellation, not
 * geometry.
 *
 * Reduced motion is a hard floor: `freeze()` puts the machine in `frozen`,
 * where every motion command is a no-op except a small in-place emote
 * acknowledgment (SPR-10's reduced-motion path). The mascot calls freeze()
 * whenever its reduced-motion guard is active, so the stage can never produce
 * involuntary motion the mascot's own guard wouldn't.
 */

export interface StageHost {
  /**
   * Walk the mascot to (x,y) in viewport coordinates, easing over `durationMs`
   * with the walking gait visibly on (the host swaps in werner-waddle). The
   * host clamps the target to the viewport itself (reusing its own clamp), so
   * the stage never needs viewport math. Resolves/settles by calling the
   * arrival callback the stage passed via `onArrive`; the host does not need
   * to await.
   */
  walkTo: (x: number, y: number, durationMs: number) => void;
  /** The current mascot position (read-only view of the host's `pos` ref). */
  getPos: () => { x: number; y: number };
  /** Show/clear an emote mark overlaid on the Werner mark. null clears. */
  setEmote: (kind: EmoteKind | null) => void;
  /** Toggle the ambient cursor-bias on the host's roam (follow on/off). */
  setFollowing: (on: boolean) => void;
  /** Pause the host's autonomous roam during a directed walk; resume after. */
  setRoamPaused: (paused: boolean) => void;
}

/** How long a directed waddle-to-target takes. Matches the host's stroll
 *  feel (the roam uses ~2600ms); a directed walk is a touch snappier so a
 *  button bump feels responsive without darting. Tunable. */
export const WADDLE_MS = 1800;

export interface WernerStageController {
  /** Walk to an absolute viewport point, then settle to idle. */
  moveTo: (x: number, y: number) => void;
  /**
   * Walk to an element's center (its bounding rect), then play `emote`
   * (default "hit"), then return to the prior ambient state. The SPR-10
   * choreography primitive. Off-screen / zero-size element → graceful no-op.
   */
  waddleToEl: (el: Element | null, emote?: EmoteKind) => void;
  /** Play a one-shot emote in place, then resume the prior ambient state. */
  emote: (kind: EmoteKind) => void;
  /** Turn ambient cursor-follow on/off. */
  follow: (on: boolean) => void;
  /** Force back to rest, cancelling any in-flight directed action. */
  idle: () => void;
  /** Reduced motion / hidden tab — clamp to the still floor. */
  freeze: () => void;
  /** Clear the freeze (reduced motion off / tab visible). */
  unfreeze: () => void;
  /** Current machine state (for tests + the mascot's render). */
  getState: () => WernerState;
  /** Tear down timers (mascot unmount). */
  dispose: () => void;
}

interface Timers {
  setTimeout: (fn: () => void, ms: number) => number;
  clearTimeout: (id: number) => void;
}

const defaultTimers: Timers = {
  setTimeout: (fn, ms) => window.setTimeout(fn, ms),
  clearTimeout: (id) => window.clearTimeout(id),
};

export function createWernerStage(
  host: StageHost,
  timers: Timers = defaultTimers,
): WernerStageController {
  let state: WernerState = INITIAL_WERNER_STATE;
  // The single in-flight directed-action timer. ONE token: a new command
  // clears the old one before scheduling, which is the latest-wins guarantee
  // (rapid activations can't stack into a queue of waddles). Never a loop.
  let actionTimer: number | null = null;

  const clearAction = () => {
    if (actionTimer !== null) {
      timers.clearTimeout(actionTimer);
      actionTimer = null;
    }
  };

  const dispatch = (event: Parameters<typeof wernerReducer>[1]) => {
    state = wernerReducer(state, event);
  };

  const moveTo = (x: number, y: number) => {
    if (state.name === "frozen") return; // reduced motion: no directed motion
    clearAction();
    dispatch({ type: "waddle" });
    host.setRoamPaused(true);
    host.setEmote(null);
    host.walkTo(x, y, WADDLE_MS);
    actionTimer = timers.setTimeout(() => {
      actionTimer = null;
      dispatch({ type: "arrived" });
      host.setRoamPaused(false);
    }, WADDLE_MS);
  };

  const playEmote = (kind: EmoteKind, resumeRoam: boolean) => {
    // Used both standalone (emote) and as the tail of a waddle. Caller has
    // already advanced the machine to `emoting`.
    host.setEmote(kind);
    const dur = emoteDurationMs(kind);
    actionTimer = timers.setTimeout(() => {
      actionTimer = null;
      host.setEmote(null);
      dispatch({ type: "emoteDone" });
      if (resumeRoam) host.setRoamPaused(false);
    }, dur);
  };

  const emote = (kind: EmoteKind) => {
    clearAction();
    if (state.name === "frozen") {
      // Reduced-motion acknowledgment: flash the STILL emote variant briefly,
      // no motion (EmoteView renders the still pose while reduced). We keep the
      // machine in `frozen` so nothing else can start moving. Still pose clears
      // after the beat so Werner returns to his frozen idle frame.
      host.setEmote(kind);
      actionTimer = timers.setTimeout(() => {
        actionTimer = null;
        host.setEmote(null);
      }, emoteDurationMs(kind));
      return;
    }
    dispatch({ type: "emote" });
    playEmote(kind, false);
  };

  const moveThenEmote = (x: number, y: number, kind: EmoteKind) => {
    clearAction();
    dispatch({ type: "waddle" });
    host.setRoamPaused(true);
    host.setEmote(null);
    host.walkTo(x, y, WADDLE_MS);
    actionTimer = timers.setTimeout(() => {
      actionTimer = null;
      dispatch({ type: "arrived" });
      // Chain straight into the emote at the target; resume roam when it ends.
      dispatch({ type: "emote" });
      playEmote(kind, true);
    }, WADDLE_MS);
  };

  const waddleToEl = (el: Element | null, kind: EmoteKind = "hit") => {
    if (state.name === "frozen") {
      // Reduced motion: NO screen-crossing waddle. A small in-place
      // acknowledgment emote instead (SPR-10 reduced-motion path).
      emote(kind);
      return;
    }
    if (!el) return; // missing target → graceful no-op (no throw)
    const rect = el.getBoundingClientRect();
    // Off-screen or zero-size (display:none, detached, scrolled away) → no-op
    // rather than waddling to (0,0) or off the edge.
    if (rect.width === 0 && rect.height === 0) return;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const vw = typeof window !== "undefined" ? window.innerWidth : 1440;
    const vh = typeof window !== "undefined" ? window.innerHeight : 900;
    if (cx < 0 || cy < 0 || cx > vw || cy > vh) return; // center off-screen → no-op
    moveThenEmote(cx, cy, kind);
  };

  const follow = (on: boolean) => {
    if (state.name === "frozen") return;
    dispatch({ type: "follow", on });
    host.setFollowing(on);
  };

  const idle = () => {
    clearAction();
    host.setEmote(null);
    if (state.name !== "frozen") {
      dispatch({ type: "idle" });
      host.setRoamPaused(false);
    }
  };

  const freeze = () => {
    clearAction();
    dispatch({ type: "freeze" });
    host.setEmote(null);
    host.setFollowing(false);
    host.setRoamPaused(false);
  };

  const unfreeze = () => {
    dispatch({ type: "unfreeze" });
  };

  const dispose = () => {
    clearAction();
  };

  return {
    moveTo,
    waddleToEl,
    emote,
    follow,
    idle,
    freeze,
    unfreeze,
    getState: () => state,
    dispose,
  };
}

export { isBusy };
