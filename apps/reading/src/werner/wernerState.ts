/**
 * Werner steering state machine (SPR-05) — the pure core.
 *
 * This is the engine's only authority on "what is Werner doing right now".
 * It is deliberately framework-free: no React, no DOM, no timers. The
 * imperative seam (WernerStage.ts) owns the side effects (moving the
 * mascot's position ref, swapping gait classes, mounting an emote); this
 * reducer owns only the *decision* about which state a command lands in,
 * so the transition rules can be unit-tested without a renderer.
 *
 * One penguin, one state. WernerStage never tracks a parallel notion of
 * "busy" — it reads this. That keeps the two halves from drifting (the
 * failure mode where the controller thinks it's idle while a stale walk
 * timer is still firing).
 *
 * States:
 *   idle       — at rest; the mascot's own autonomous roam owns position.
 *   following  — biasing the roam toward the lagged cursor (still ambient).
 *   waddling   — a directed walk to a specific target (choreography / moveTo).
 *   emoting    — playing a one-shot emote mark; returns to its prior ambient
 *                state (idle or following) when the beat ends.
 *   frozen     — reduced-motion / hidden tab: no involuntary motion at all.
 *
 * `frozen` is a hard floor: every command is a no-op while frozen except
 * `unfreeze`, which returns to `idle`. This is the single chokepoint that
 * makes "no involuntary motion under reduced motion" provable — a caller
 * cannot accidentally route around it, because there is no other path out
 * of `frozen`.
 */

export type WernerStateName =
  | "idle"
  | "following"
  | "waddling"
  | "emoting"
  | "frozen";

/** The ambient state Werner falls back to after a directed action ends.
 *  Only the two ambient states are valid resumptions — you never "resume"
 *  into waddling or emoting. */
export type AmbientState = "idle" | "following";

export interface WernerState {
  readonly name: WernerStateName;
  /**
   * Where to return after a one-shot (`emoting`, or a directed `waddling`):
   * the ambient state that was active when the action began. Carrying it on
   * the state — rather than recomputing it on completion — means an `emote`
   * fired mid-follow resumes following, not a hard idle (the failure mode
   * where every emote silently cancels mouse-following).
   */
  readonly resume: AmbientState;
}

export type WernerEvent =
  /** Begin biasing the ambient roam toward the lagged cursor. */
  | { type: "follow"; on: boolean }
  /** Directed walk to a target (choreography waddle-to-button, or moveTo). */
  | { type: "waddle" }
  /** Play a one-shot emote. */
  | { type: "emote" }
  /** The directed walk reported arrival. */
  | { type: "arrived" }
  /** The one-shot emote beat ended. */
  | { type: "emoteDone" }
  /** Force back to rest (e.g. choreography returns to idle, or a cancel). */
  | { type: "idle" }
  /** Reduced motion / hidden tab — clamp to the still floor. */
  | { type: "freeze" }
  /** Reduced motion cleared / tab visible again. */
  | { type: "unfreeze" };

export const INITIAL_WERNER_STATE: WernerState = { name: "idle", resume: "idle" };

/** The ambient state implied by a name, for computing `resume`. A directed
 *  or one-shot state inherits the resume already on the state. */
function ambientOf(s: WernerState): AmbientState {
  if (s.name === "following") return "following";
  if (s.name === "idle") return "idle";
  // mid-action: keep whatever ambient we were heading back to.
  return s.resume;
}

/**
 * The transition function. Total + pure: every (state, event) pair has a
 * defined result (unknown combinations are a no-op rather than a throw, so
 * a stray late event from a cancelled action can never crash the engine).
 */
export function wernerReducer(
  state: WernerState,
  event: WernerEvent,
): WernerState {
  // `frozen` is the hard floor — only `unfreeze` escapes it. Everything else
  // is swallowed so reduced motion can never be routed around.
  if (state.name === "frozen") {
    return event.type === "unfreeze" ? INITIAL_WERNER_STATE : state;
  }

  switch (event.type) {
    case "freeze":
      return { name: "frozen", resume: "idle" };

    case "unfreeze":
      // Already unfrozen — no-op (idempotent).
      return state;

    case "follow": {
      // Toggling follow only moves the ambient floor. If a directed action is
      // in flight (waddling/emoting) we DON'T interrupt it — we just record
      // the ambient to resume into, so the action lands in the right place.
      const nextAmbient: AmbientState = event.on ? "following" : "idle";
      if (state.name === "idle" || state.name === "following") {
        return { name: nextAmbient, resume: nextAmbient };
      }
      return { ...state, resume: nextAmbient };
    }

    case "waddle":
      // A directed walk supersedes any in-flight action (latest-wins). Resume
      // back into whatever ambient we were in.
      return { name: "waddling", resume: ambientOf(state) };

    case "emote":
      // An emote supersedes an in-flight emote/waddle (latest-wins) but keeps
      // the ambient to resume into.
      return { name: "emoting", resume: ambientOf(state) };

    case "arrived":
      // Only meaningful while waddling; otherwise a stale late arrival is
      // ignored (the walk it belonged to was already superseded).
      return state.name === "waddling"
        ? { name: state.resume, resume: state.resume }
        : state;

    case "emoteDone":
      return state.name === "emoting"
        ? { name: state.resume, resume: state.resume }
        : state;

    case "idle":
      // Hard return to rest — used on cancel / choreography completion.
      return { name: "idle", resume: "idle" };

    default:
      return state;
  }
}

/** True while Werner is doing something directed (not just ambient roam). */
export function isBusy(state: WernerState): boolean {
  return state.name === "waddling" || state.name === "emoting";
}
