import {
  REEL_MAX_PX_PER_S,
  REEL_SETTLE_EPSILON_PX,
  REEL_SPRING_MASS,
  REEL_SPRING_OMEGA_RAD_PER_S,
  REEL_TAU_MS,
} from "./iceFishingConstants";

export interface Vec2 {
  x: number;
  y: number;
}

/**
 * Reel integrator config (SPR-03).
 *
 * `mode` selects the dynamics:
 *   - "spring"      (DEFAULT) — critically-damped spring; accelerates off the
 *                   mark, decelerates as it nears, settles with no overshoot.
 *                   Reads as a line with mass. This is what the operator asked
 *                   for ("the pull should get slower as it closes").
 *   - "exponential" — the original first-order ease (SPR-15). Kept as a
 *                   documented FALLBACK: deterministic, one fewer state field,
 *                   and a slower tau alone DOES read as slower. Flip
 *                   `DEFAULT_REEL_CONFIG.mode` (or pass `{ mode: "exponential" }`)
 *                   to ship the cheaper change if the spring ever stops earning
 *                   its keep. See the steelman in the SPR-03 handoff.
 *
 * Both modes share the velocity cap (`maxPxPerS`) as a teleport safety clamp.
 */
export interface ReelConfig {
  mode: "spring" | "exponential";
  /** Exponential-mode time constant (ms). Origin: REEL_TAU_MS. */
  tauMs: number;
  /** Spring natural frequency (rad/s). Origin: REEL_SPRING_OMEGA_RAD_PER_S. */
  omega: number;
  /** Spring mass (px·s²-equivalent units). Origin: REEL_SPRING_MASS. */
  mass: number;
  /** Velocity cap (px/s) — teleport safety clamp for both modes. */
  maxPxPerS: number;
}

export const DEFAULT_REEL_CONFIG: ReelConfig = {
  mode: "spring",
  tauMs: REEL_TAU_MS,
  omega: REEL_SPRING_OMEGA_RAD_PER_S,
  mass: REEL_SPRING_MASS,
  maxPxPerS: REEL_MAX_PX_PER_S,
};

/**
 * Spring reel state: position AND velocity. The velocity is what gives the
 * pull mass — it ramps up off the mark and bleeds off as the spring settles.
 * The exponential path carries no velocity (vx/vy stay 0).
 */
export interface ReelState {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/** Lift a bare position into a fresh, at-rest reel state (zero velocity). */
export function makeReelState(pos: Vec2): ReelState {
  return { x: pos.x, y: pos.y, vx: 0, vy: 0 };
}

/**
 * Largest dtMs the integrator will ever honour in a single call.
 *
 * Origin / why: tabs that go to background, debugger pauses, and dragged
 * windows all produce one enormous frame gap on return. Integrating that whole
 * gap would make the spring lurch in a straight line to "catch up" (M4: the
 * no-catch-up-lurch requirement). We clamp dt to ~3 frames at 60Hz: long
 * enough that a couple of dropped frames still integrate smoothly, short enough
 * that a post-stall gap snaps the integrator forward by at most this slice
 * rather than teleporting. The rAF caller in PenguinMascot ALSO clamps (belt +
 * braces); this clamp makes the PURE integrator robust on its own.
 */
export const REEL_MAX_DT_MS = 48;

/**
 * Sub-step size (ms) for the spring's semi-implicit Euler integration.
 *
 * Origin / why: semi-implicit (symplectic) Euler is unconditionally stable for
 * a critically-damped spring only when ω₀·dt is small. At ω₀ = 5 rad/s a single
 * 48ms step gives ω₀·dt ≈ 0.24, which is fine, but stepping in ≤16ms slices
 * keeps the discrete trajectory faithful to the continuous one across the full
 * dt-sweep the no-overshoot test exercises (so the proof isn't an artifact of a
 * coarse step). 16ms ≈ one 60Hz frame.
 */
const SPRING_SUBSTEP_MS = 16;

function clampVelocityCap(vx: number, vy: number, maxPxPerS: number): Vec2 {
  const speed = Math.hypot(vx, vy);
  const maxSpeed = maxPxPerS; // px/s
  if (speed > maxSpeed && speed > 0) {
    const s = maxSpeed / speed;
    return { x: vx * s, y: vy * s };
  }
  return { x: vx, y: vy };
}

/**
 * One first-order exponential step toward the lagged hook (the SPR-15 path,
 * now the documented FALLBACK). `alpha = 1 - exp(-dtMs / tauMs)`. Never reads
 * the live pointer — `target` is the lagged hook.
 *
 * Pure + deterministic: (pos, target, dtMs) in, pos out. No Date.now /
 * Math.random. Velocity cap preserved as a teleport clamp.
 */
export function reelStep(
  pos: Vec2,
  target: Vec2,
  dtMs: number,
  cfg: ReelConfig = DEFAULT_REEL_CONFIG,
): Vec2 {
  if (dtMs <= 0) return pos;
  // Clamp post-stall gaps (M4) so a huge dt can't haul Werner across in one go.
  const dt = Math.min(dtMs, REEL_MAX_DT_MS);
  const alpha = 1 - Math.exp(-dt / cfg.tauMs);
  let dx = (target.x - pos.x) * alpha;
  let dy = (target.y - pos.y) * alpha;
  const maxStep = (cfg.maxPxPerS * dt) / 1000;
  const mag = Math.hypot(dx, dy);
  if (mag > maxStep && mag > 0) {
    const s = maxStep / mag;
    dx *= s;
    dy *= s;
  }
  return { x: pos.x + dx, y: pos.y + dy };
}

/**
 * One critically-damped spring step toward the lagged hook (SPR-03 DEFAULT).
 *
 * Physics. A unit-mass point on a spring of stiffness k toward `target`, damped
 * by c:
 *     a = (−k·displacement − c·velocity) / m
 * Critical damping is c = 2·√(k·m): the unique damping that returns to rest in
 * the SHORTEST time with NO overshoot (under-damped overshoots, over-damped
 * crawls). With ω₀ = √(k/m) the closed form has envelope (1 + ω₀·t)·e^(−ω₀·t),
 * which is monotone toward the target — hence the test can assert the position
 * never passes it. We DERIVE k and c from (mass, omega) so the felt-weight knob
 * stays a single number:
 *     k = m·ω₀²        c = 2·√(k·m) = 2·m·ω₀
 *
 * Integration. Semi-implicit (symplectic) Euler, sub-stepped at ≤16ms: update
 * velocity from the current displacement, THEN move position by the new
 * velocity. This ordering is what keeps a discrete critically-damped spring
 * from overshooting (explicit Euler can inject energy and overshoot; symplectic
 * does not). dtMs is clamped to REEL_MAX_DT_MS first (M4: no catch-up lurch),
 * then the velocity cap bounds the per-step displacement as a final teleport
 * safety clamp.
 *
 * Pure + deterministic: (state, target, dtMs) in, new state out. No Date.now /
 * Math.random inside the integrator.
 */
export function reelSpringStep(
  state: ReelState,
  target: Vec2,
  dtMs: number,
  cfg: ReelConfig = DEFAULT_REEL_CONFIG,
): ReelState {
  if (dtMs <= 0) return state;

  const m = cfg.mass;
  const omega = cfg.omega;
  const k = m * omega * omega; // k = m·ω₀²
  const c = 2 * m * omega; // c = 2·√(k·m) = 2·m·ω₀ (exactly critical)

  // M4: clamp the post-stall gap before integrating.
  let remaining = Math.min(dtMs, REEL_MAX_DT_MS);

  let { x, y, vx, vy } = state;

  while (remaining > 0) {
    const h = Math.min(SPRING_SUBSTEP_MS, remaining) / 1000; // seconds
    remaining -= SPRING_SUBSTEP_MS;

    // Acceleration from the CURRENT displacement + velocity.
    const ax = (-k * (x - target.x) - c * vx) / m;
    const ay = (-k * (y - target.y) - c * vy) / m;

    // Semi-implicit Euler: advance velocity first, then position with it.
    vx += ax * h;
    vy += ay * h;

    // Velocity cap (teleport safety clamp) applied to the spring velocity.
    const capped = clampVelocityCap(vx, vy, cfg.maxPxPerS);
    vx = capped.x;
    vy = capped.y;

    x += vx * h;
    y += vy * h;
  }

  return { x, y, vx, vy };
}

/**
 * Integrator-agnostic reel step. Routes by `cfg.mode` and keeps the spring's
 * velocity across calls. PenguinMascot drives this so swapping the mode is a
 * one-line config flip, not a call-site change.
 */
export function reelStateStep(
  state: ReelState,
  target: Vec2,
  dtMs: number,
  cfg: ReelConfig = DEFAULT_REEL_CONFIG,
): ReelState {
  if (cfg.mode === "exponential") {
    const next = reelStep({ x: state.x, y: state.y }, target, dtMs, cfg);
    // The router must return a full ReelState regardless of mode so its shape
    // is identical across modes (callers store one `{x,y,vx,vy}` and never
    // branch on mode). We synthesize the velocity from the position delta so
    // that field is honest for debug reads; the exponential path ignores vx/vy
    // on its next call (reelStep reads only position). NOTE: isReelSettled takes
    // a POSITION only and never reads velocity — this synthesized vx/vy is for
    // the consistent-shape contract, not for any settle check.
    const dt = Math.min(dtMs, REEL_MAX_DT_MS);
    const vx = dt > 0 ? ((next.x - state.x) * 1000) / dt : 0;
    const vy = dt > 0 ? ((next.y - state.y) * 1000) / dt : 0;
    return { x: next.x, y: next.y, vx, vy };
  }
  return reelSpringStep(state, target, dtMs, cfg);
}

export function isReelSettled(
  pos: Vec2,
  target: Vec2,
  epsilon = REEL_SETTLE_EPSILON_PX,
): boolean {
  return Math.hypot(target.x - pos.x, target.y - pos.y) <= epsilon;
}
