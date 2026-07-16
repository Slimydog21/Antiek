/**
 * Living-TV ambient — quiet-period idle beat for Werner.
 *
 * Antiek is the home of the penguin: when the product is quiet for a while,
 * the asynchronous TV show takes a soft idle/sleeping glance. Never chases
 * the cursor; never auto-starts games. Pure policy is unit-tested; the
 * installer wires timers + emitWernerExperience.
 */

import { emitWernerExperience, type ProductExperience } from "./reactionBus";

/** Default quiet window before ambient idle (90s). */
export const DEFAULT_AMBIENT_QUIET_MS = 90_000;

/**
 * Pure policy: after `quietMs` without product experiences, return the ambient
 * experience to emit once. Null means stay silent.
 */
export function ambientExperienceAfterQuiet(
  quietMs: number,
  thresholdMs: number = DEFAULT_AMBIENT_QUIET_MS,
): ProductExperience | null {
  if (!Number.isFinite(quietMs) || quietMs < 0) return null;
  if (quietMs < thresholdMs) return null;
  return "idle";
}

export interface LivingTvAmbientOptions {
  /** Quiet threshold before ambient idle. Default 90s. */
  quietMs?: number;
  /** Poll interval for quiet clock. Default 5s. */
  pollMs?: number;
  /** Inject emit for tests. */
  emit?: (experience: ProductExperience) => void;
  /** Inject timers for tests. */
  setInterval?: (fn: () => void, ms: number) => number;
  clearInterval?: (id: number) => void;
  /** Inject now() for tests. */
  now?: () => number;
  /**
   * Event target for product experiences (resets the quiet clock).
   * Defaults to window when available.
   */
  target?: Pick<Window, "addEventListener" | "removeEventListener"> | null;
}

/**
 * Install ambient living-TV heartbeat. Resets on any antiek:werner-experience.
 * Emits at most one idle per quiet window (re-arms after each product beat).
 */
export function installLivingTvAmbient(
  options: LivingTvAmbientOptions = {},
): () => void {
  const quietThreshold = options.quietMs ?? DEFAULT_AMBIENT_QUIET_MS;
  const pollMs = options.pollMs ?? 5_000;
  const emit = options.emit ?? emitWernerExperience;
  const setInt =
    options.setInterval ??
    ((fn: () => void, ms: number) => window.setInterval(fn, ms));
  const clearInt =
    options.clearInterval ?? ((id: number) => window.clearInterval(id));
  const now = options.now ?? (() => Date.now());
  const target =
    options.target === undefined
      ? typeof window !== "undefined"
        ? window
        : null
      : options.target;

  let lastBeat = now();
  let armed = true;

  const onExperience = () => {
    lastBeat = now();
    armed = true;
  };

  if (target) {
    target.addEventListener(
      "antiek:werner-experience",
      onExperience as EventListener,
    );
  }

  const timerId = setInt(() => {
    const quietMs = now() - lastBeat;
    const next = ambientExperienceAfterQuiet(quietMs, quietThreshold);
    if (next && armed) {
      armed = false;
      emit(next);
      lastBeat = now();
    }
  }, pollMs);

  return () => {
    clearInt(timerId);
    if (target) {
      target.removeEventListener(
        "antiek:werner-experience",
        onExperience as EventListener,
      );
    }
  };
}
