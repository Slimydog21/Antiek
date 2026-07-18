/**
 * Living-TV ambient — quiet-period episode continuity for Werner.
 *
 * Antiek is the home of the penguin (Flipbook-feel invent strips live in HTML;
 * pure Flipbook sole UI is NO-GO): when the product is quiet for a while,
 * the asynchronous TV show takes a soft ambient glance that continues the
 * last product "episode" (not a generic always-idle loop). Never chases
 * the cursor; never auto-starts games. Pure policy is unit-tested; the
 * installer wires timers + emitWernerExperience.
 */

import {
  emitWernerExperience,
  isProductExperience,
  type ProductExperience,
  type WernerExperienceDetail,
  WERNER_EXPERIENCE_EVENT,
} from "./reactionBus";

/** Default quiet window before ambient episode (90s). */
export const DEFAULT_AMBIENT_QUIET_MS = 90_000;

/**
 * Pure policy: after `quietMs` without product experiences, return the ambient
 * experience that continues the last episode. Null means stay silent.
 *
 * Episode continuity (hard to vary):
 * - deep_research_start → idle (sleep while research runs)
 * - deep_research_complete / piece_started → note_saved (soft pride savor)
 * - note_saved → idle (curtain call: sleep after pride; no ambient spam loop)
 * - fail / deep_research_error → idle (recover)
 * - idle (already ambient curtain) → null (no ambient spam loop)
 * - default / null → idle
 *
 * Living-TV show structure: product beat → pride savor (when earned) →
 * curtain idle → silence. Cursor never auto-starts games; pure Flipbook sole
 * UI remains NO-GO (HTML Flipbook-feel invent strips only).
 */
export function ambientExperienceAfterQuiet(
  quietMs: number,
  thresholdMs: number = DEFAULT_AMBIENT_QUIET_MS,
  lastExperience: ProductExperience | null = null,
): ProductExperience | null {
  if (!Number.isFinite(quietMs) || quietMs < 0) return null;
  if (quietMs < thresholdMs) return null;
  // Already showed ambient idle — stay silent until a real product beat.
  if (lastExperience === "idle") return null;
  switch (lastExperience) {
    case "deep_research_complete":
    case "piece_started":
      return "note_saved";
    case "deep_research_start":
    case "fail":
    case "deep_research_error":
    case "highlight":
    case "note_saved":
    case null:
    default:
      return "idle";
  }
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
 * Install ambient living-TV heartbeat with episode continuity.
 * Resets on any antiek:werner-experience. Emits at most one ambient beat
 * per quiet window (re-arms after each product beat).
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
  let lastExperience: ProductExperience | null = null;

  const onExperience = (event: Event) => {
    lastBeat = now();
    armed = true;
    const detail = (event as CustomEvent<Partial<WernerExperienceDetail>>)
      .detail;
    const exp = detail?.experience;
    if (isProductExperience(exp)) {
      lastExperience = exp;
    }
  };

  if (target) {
    target.addEventListener(
      WERNER_EXPERIENCE_EVENT,
      onExperience as EventListener,
    );
  }

  const timerId = setInt(() => {
    const quietMs = now() - lastBeat;
    const next = ambientExperienceAfterQuiet(
      quietMs,
      quietThreshold,
      lastExperience,
    );
    if (next && armed) {
      lastExperience = next;
      emit(next);
      lastBeat = now();
      // Curtain call densify: after pride savor, re-arm once so a second quiet
      // window can sleep (idle) and then silence — living-TV episode end credits.
      // Idle never re-arms (no ambient spam loop). Product beats re-arm via
      // onExperience.
      armed = next === "note_saved";
    }
  }, pollMs);

  return () => {
    clearInt(timerId);
    if (target) {
      target.removeEventListener(
        WERNER_EXPERIENCE_EVENT,
        onExperience as EventListener,
      );
    }
  };
}
