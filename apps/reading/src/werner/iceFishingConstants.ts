/** WERNER-ICE lag budget (master spec). */

/**
 * Reel time constant for the EXPONENTIAL fallback (SPR-03).
 *
 * Felt target: a slower, weightier pull. Raised 450 → 950ms — at the slow
 * end of the master-spec ~900–1100 window. 950 is chosen deliberately so the
 * exponential's settle still lands inside the synthetic 950ms handoff budget
 * (PenguinMascot.iceFishing.test.tsx) from a near-hook start, while reading as
 * noticeably heavier than the old snappy 450. A 950ms exponential closes only
 * ~63% of the gap per tau, so the first half-second covers far fewer pixels
 * than the 450 baseline did — that "fewer-px-up-front" delta is the mechanical
 * proof of "slower" (reelPursuit.test.ts). The default reel is the SPRING
 * (REEL_SPRING_OMEGA_RAD_PER_S); this tau only governs the documented fallback.
 */
export const REEL_TAU_MS = 950;

/**
 * Velocity cap (safety clamp) for BOTH integrators. Lowered 480 → 360 px/s.
 *
 * Felt target: stop the cap from masking the new slower easing on long pulls.
 * The old 480 cap let a far-away hook get hauled in at a flat top speed before
 * the easing ever took over, which read as a constant-speed drag, not a weighty
 * accelerate-then-settle. 360 px/s keeps the cap as a teleport guard (a hook
 * jump still can't make Werner streak across the screen in one frame) while
 * sitting above the spring's natural peak speed for normal-distance pulls, so
 * on those the cap never engages and the deceleration the operator asked for is
 * fully visible. Tuned to be inert for in-viewport pulls, active only on
 * teleport-scale gaps.
 */
export const REEL_MAX_PX_PER_S = 360;

/**
 * Settle radius: Werner is "on the hook" within this many px. Unchanged at 8.
 * The slower pull is about the APPROACH, not the resting threshold; moving this
 * would change when the reel reports done, not how heavy the pull feels.
 */
export const REEL_SETTLE_EPSILON_PX = 8;

/**
 * Critically-damped spring reel (SPR-03, the DEFAULT integrator).
 *
 * Model: a unit mass on a spring toward the lagged hook, damped at exactly
 * critical (c = 2·√(k·m)) so it is the FASTEST settle with NO overshoot — a
 * line under tension that accelerates off the mark then softly settles.
 *
 * We parameterize by the natural frequency ω₀ = √(k/m) rather than raw k,
 * because ω₀ IS the felt-weight knob: the critically-damped step response is
 * 1 − (1 + ω₀·t)·e^(−ω₀·t), so settle time ≈ 5/ω₀ and a full close ≈ 6/ω₀.
 * With m = 1:
 *   ω₀ = 5.0 rad/s  →  settle ≈ 5/5 = 1.0s, full close ≈ 6/5 = 1.2s.
 *   k  = m·ω₀²       = 25.0   (spring stiffness; derived, see reelPursuit.ts)
 *   c  = 2·√(k·m)    = 10.0   (critical damping; derived, see reelPursuit.ts)
 * WHY 5.0, not higher: a critically-damped spring accelerates HARD off the
 * mark. At ω₀ = 6 the spring covered MORE pixels in the first 300ms than the
 * old 450ms exponential — i.e. it read FASTER off the mark, the opposite of the
 * operator's ask, even though it settled with weight. ω₀ = 5.0 is the chosen
 * point where the spring closes FEWER pixels than the 450 baseline in the first
 * 300ms (the mechanical "slower" proof in reelPursuit.test.ts) AND still
 * decelerates into a soft, overshoot-free settle (the "weighty" proof). It is
 * the largest ω₀ that keeps BOTH true — heavier/slower below it, "faster off
 * the mark" above it. m stays 1: absolute mass only rescales k and c together,
 * so 1 keeps the numbers legible.
 */
export const REEL_SPRING_OMEGA_RAD_PER_S = 5.0;
export const REEL_SPRING_MASS = 1.0;

/** Idle roam only — restored from pre-snappy-follow values (SPR-15). */
export const ROAM_STROLL_MS = 1400;
export const ROAM_REST_MIN_MS = 1200;
export const ROAM_REST_MAX_MS = 2800;
