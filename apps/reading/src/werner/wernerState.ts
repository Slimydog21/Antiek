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

/* ════════════════════════════════════════════════════════════════════════
 * SPR-05 — THE ENDLESS FISHING LOOP (the Scrat / Tom-&-Jerry cycle).
 *
 * Operator ask #3: when left alone, Werner runs a comic gag of trying to fish
 * and never quite catching — forever. This is his POINTER-IDLE behaviour: the
 * cursor is the bait, so when the pointer MOVES Werner reels toward it (SPR-03);
 * when the pointer is IDLE he drops the chase and runs THIS gag against his own
 * little fish, and never lands it.
 *
 * Master decision log: the loop is the pointer-IDLE behaviour — see the SPR-05
 * sprint page (sprint-05-endless-fishing-loop.html, "Parent context": "The
 * whole point of this sprint is what Werner does when nobody is moving the
 * mouse"). DO NOT "fix" the loop to run during follow — that re-opens that
 * decision. The loop is gated OFF whenever the reel owns Werner.
 *
 * ── STANDALONE ADAPTATION (read before editing) ──────────────────────────
 * The spec's SPR-05 assumed SPR-01 had turned wernerState.ts into a typed POSE
 * machine (cast/wait/nibble/yank/miss/slump). SPR-01 IS DEFERRED. The real
 * machine above is a STEERING machine (it decides WHAT Werner does, not pose
 * interpolation). So the cartoon is expressed two ways, split by concern:
 *
 *   1. GATING (this file, `shouldFish`): a pure predicate that decides when the
 *      loop OWNS Werner — only while the ambient state is `idle` (never
 *      following/waddling/emoting/frozen) AND the pointer is idle. It reuses the
 *      EXISTING pointer-idle signal (useMouseFollow.pointerIdle); it does NOT
 *      re-detect idle and adds NO new timer. A pointer move flips
 *      `pointerIdle → false`, `shouldFish → false`, and the reel takes over —
 *      one owner at a time, by construction (the predicate is the XOR).
 *
 *   2. CYCLE STRUCTURE (this file, `FISHING_BEATS` + `fishingStep`): the comic
 *      cartoon as DATA — an ordered beat table with a commented holdMs per beat
 *      (the comic timing) and a pure clock-injected sequencer that maps elapsed
 *      ms → the current beat. The animation itself is a CSS keyframe sequence
 *      (waddle.css) on the SPR-04 rod <g> + a fish mark + the line; this table
 *      is the deterministic, unit-testable shadow of it (beat order, total
 *      period, that it LOOPS, and the never-caught invariant). A future SPR-01
 *      pose machine can lift this table verbatim — it is the engine-independent
 *      spec of the gag.
 *
 * Defensibility: the cycle is DATA. To retune the slump or add a "double-take",
 * a maintainer edits FISHING_BEATS (and the matching waddle.css keyframe %),
 * never the sequencer. The beat % offsets in waddle.css are derived from these
 * same holdMs values — keep them in sync (the comment on each beat says where).
 * ════════════════════════════════════════════════════════════════════════ */

/** The named beats of the never-catch gag, in cycle order. `reset` returns the
 *  rod/line/fish to neutral so the next `cast` starts clean — it is NOT a
 *  "caught" payoff (there is none, by design). */
export type FishingBeat =
  | "cast" // wind up + swing the rod out, line extends
  | "wait" // held stillness — the comic beat of nothing happening
  | "bob" // the fish drifts in; the bobber dips
  | "nibble" // the near-catch: the fish mouths the hook (HOPE)
  | "yank" // the fast hopeful pull — rod bends hard, line snaps up
  | "miss" // the line flies up EMPTY; the fish darts away (the gag)
  | "slump" // the slow disappointed settle
  | "reset"; // ease everything back to neutral, then loop to `cast`

/** A beat plus how long it holds, with the comic-timing rationale. The order of
 *  this array IS the cycle order; the loop runs it forever and never reaches a
 *  "caught" terminal (there is no such beat). */
export interface FishingBeatStep {
  readonly beat: FishingBeat;
  /** How long this beat holds, in ms. */
  readonly holdMs: number;
  /** Why this duration — the comic beat it serves (Tom-&-Jerry timing). */
  readonly intent: string;
}

/**
 * THE GAG, AS DATA. Tom-&-Jerry comic timing: a slow anticipatory wind-up, a
 * long HELD beat of nothing, a fast snap of false hope, then a long disappointed
 * settle. The fast beats (nibble→yank→miss) are deliberately short so the
 * near-catch reads as a SNAP the eye almost misses — that is what sells "almost
 * had it". The slow beats (wait, slump) are long so the held stillness and the
 * dejection read as deliberate timing, not a stutter.
 *
 * Total period ≈ 6.4s — slow enough to read as a deliberate cartoon a human can
 * follow, fast enough that a watcher sees a full cycle before looking away. The
 * waddle.css keyframe %s are these holdMs as fractions of the total (see each
 * beat's comment); edit BOTH together.
 */
export const FISHING_BEATS: readonly FishingBeatStep[] = [
  {
    beat: "cast",
    holdMs: 900, // SLOW wind-up — the anticipatory swing; ~0–14% of the cycle.
    intent: "slow anticipatory wind-up: the rod swings out, the line extends",
  },
  {
    beat: "wait",
    holdMs: 1600, // LONG held beat — the comic stillness; ~14–39%.
    intent: "held beat of nothing happening — the longest beat, sells the wait",
  },
  {
    beat: "bob",
    holdMs: 700, // the fish drifts in; gentle expectation; ~39–50%.
    intent: "the fish approaches, the bobber dips — rising expectation",
  },
  {
    beat: "nibble",
    holdMs: 450, // the near-catch — HOPE; short so it reads as a flicker; ~50–57%.
    intent: "near-catch: the fish mouths the hook — the hope beat",
  },
  {
    beat: "yank",
    holdMs: 220, // FAST snap — the hopeful pull; the punchiest beat; ~57–60%.
    intent: "fast hopeful yank — rod bends hard, the eye almost misses it",
  },
  {
    beat: "miss",
    holdMs: 380, // the empty line flies up; the gag lands; ~60–66%.
    intent: "the line flies up EMPTY, the fish escapes — the miss",
  },
  {
    beat: "slump",
    holdMs: 1500, // LONG disappointed settle; ~66–90%.
    intent: "slow disappointed slump — the dejection, deliberately drawn out",
  },
  {
    beat: "reset",
    holdMs: 650, // ease back to neutral before looping; ~90–100%.
    intent: "ease the rod/line/fish back to neutral, then loop to cast",
  },
] as const;

/** Total cycle length (ms) — the sum of every beat's hold. The loop period. */
export const FISHING_CYCLE_MS: number = FISHING_BEATS.reduce(
  (acc, s) => acc + s.holdMs,
  0,
);

/**
 * Where in the cycle are we at `elapsedMs`? Pure + clock-injected (no Date.now,
 * no Math.random): the caller owns the clock and passes elapsed time since the
 * loop began. `elapsedMs` is taken modulo the cycle, so the gag LOOPS forever —
 * there is no terminal state to reach. Returns the active beat, its index, and
 * the 0..1 phase WITHIN that beat (so the CSS/render can interpolate if it wants
 * to; the keyframe animation in waddle.css is the primary driver).
 *
 * Never-caught is structural: the returned beat is always one of FISHING_BEATS,
 * none of which is "caught"; and because we mod by the period, `reset` is always
 * followed by `cast`, never by a payoff. The deterministic test walks a full
 * cycle and asserts both the order and that no "caught" beat exists.
 */
export interface FishingFrame {
  readonly beat: FishingBeat;
  readonly index: number;
  /** 0..1 progress through the current beat. */
  readonly beatPhase: number;
}

export function fishingStep(elapsedMs: number): FishingFrame {
  // Negative / NaN guard: clamp to 0 so a stray pre-mount tick is the cast.
  const e = Number.isFinite(elapsedMs) && elapsedMs > 0 ? elapsedMs : 0;
  const t = e % FISHING_CYCLE_MS;
  let acc = 0;
  for (let i = 0; i < FISHING_BEATS.length; i++) {
    const step = FISHING_BEATS[i];
    if (t < acc + step.holdMs) {
      return {
        beat: step.beat,
        index: i,
        beatPhase: (t - acc) / step.holdMs,
      };
    }
    acc += step.holdMs;
  }
  // Exactly at the period boundary (t === 0 after a full loop) — the first beat.
  return { beat: FISHING_BEATS[0].beat, index: 0, beatPhase: 0 };
}

/**
 * THE GATE. Does the fishing loop own Werner right now? This is the XOR that
 * keeps the loop and the SPR-03 reel from ever fighting: the loop runs ONLY
 * while Werner is at ambient rest (`idle`) AND the pointer is idle. The instant
 * the pointer moves, `pointerIdle` flips false here and the reel takes over; the
 * instant Werner is following / waddling / emoting / frozen, the loop stands
 * down. Exactly one owner at a time, by construction.
 *
 *   - frozen     → false (reduced motion / hidden tab: no involuntary gag).
 *   - following  → false (the reel owns him — the cursor is the live bait).
 *   - waddling   → false (a directed walk owns the position).
 *   - emoting    → false (a one-shot beat is playing).
 *   - idle       → ONLY THEN, and only while the pointer is idle.
 *
 * Pure: no timers, no idle re-detection. `pointerIdle` is the EXISTING signal
 * from useMouseFollow (POINTER_IDLE_MS); this predicate consumes it, it does not
 * recompute it. Removing the `pointerIdle` term here makes the loop run during
 * an active reel — the mutation a gating test must catch.
 */
export function shouldFish(state: WernerState, pointerIdle: boolean): boolean {
  return state.name === "idle" && pointerIdle;
}
