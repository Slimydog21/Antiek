/**
 * Pure wait-host policy (SPR-16 subset).
 *
 * - Never interrupt work: game mounts only after an explicit opt-in OR after
 *   a long-wait threshold when the parent already marked the wait as opt-in.
 * - Readiness always wins: when ready flips true, host must unmount same tick.
 * - Flag / reduced-motion / calm collapse to plain loader (no game).
 */

export type WaitHostMode = "hidden" | "plain-loader" | "offer" | "playing";

export interface WaitHostInput {
  /** True while the awaited work is still in flight. */
  waiting: boolean;
  /** True when the awaited work resolved (success or error). */
  ready: boolean;
  /** Feature flag wernerArcade. */
  arcadeEnabled: boolean;
  /** OS reduced motion or Calm — static / no game. */
  reducedOrCalm: boolean;
  /** Operator explicitly opted in to play during wait. */
  optedIn: boolean;
  /** Milliseconds spent waiting so far. */
  waitedMs: number;
  /** Threshold before auto-offer (not auto-play). */
  offerAfterMs: number;
}

/**
 * Decide the host surface. Pure function — unit tests drive this directly.
 *
 * Invariants:
 * 1. ready → hidden (teardown) regardless of other flags.
 * 2. !waiting → hidden.
 * 3. !arcadeEnabled → plain-loader while waiting (pre-existing loader path).
 * 4. reducedOrCalm → plain-loader (never auto-animate a game).
 * 5. optedIn + waiting + arcade → playing.
 * 6. waiting past threshold without opt-in → offer (explicit launch).
 * 7. else plain-loader.
 */
export function decideWaitHostMode(input: WaitHostInput): WaitHostMode {
  if (input.ready || !input.waiting) return "hidden";
  if (!input.arcadeEnabled) return "plain-loader";
  if (input.reducedOrCalm) return "plain-loader";
  if (input.optedIn) return "playing";
  if (input.waitedMs >= input.offerAfterMs) return "offer";
  return "plain-loader";
}

/** Default offer threshold — long enough to avoid flash on fast loads. */
export const DEFAULT_OFFER_AFTER_MS = 2500;

/**
 * Same-tick readiness race helper: given previous mode and new input,
 * returns whether the host must tear down the game immediately.
 */
export function mustTeardownGame(
  prev: WaitHostMode,
  next: WaitHostMode,
): boolean {
  return prev === "playing" && next !== "playing";
}
