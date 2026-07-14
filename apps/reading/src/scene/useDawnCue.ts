import type { SceneMood } from "./mood";
import { useSceneMomentCue } from "./useSceneMomentCue";

export interface SceneMomentCue {
  sequence: number;
  moment: "daybreak";
}

/**
 * Scene-side dawn cue — one typed one-shot signal emitted exactly once per
 * committed `night → dawn` transition (SPR-22).
 *
 * Owns no media, civil-time, or visibility listener: it receives the mood
 * from `useDerivedSceneMood` (the sole time/theme listener) and compares
 * the committed previous mood against the current mood after render.
 *
 * Emission discipline:
 * - Initial mount: no emission (previousRef is null → momentForTransition
 *   returns null).
 * - Same mood re-render: no emission.
 * - StrictMode: the committed previous mood suppresses duplicate effects.
 * - Unmount: no emission (cleanup does not emit).
 * - Weather-only change: no emission.
 * - night → day: no emission (momentForTransition returns null).
 * - day → dawn: no emission (momentForTransition returns null).
 * - Initial dawn: no emission (previousRef is null).
 *
 * A monotonic sequence gives the consumer an identity-safe one-shot signal.
 */
export function useDawnCue(
  mood: SceneMood,
  onTransition?: (cue: SceneMomentCue) => void,
): void {
  useSceneMomentCue(mood, (cue) => {
    if (cue.moment === "daybreak") {
      onTransition?.({ sequence: cue.sequence, moment: "daybreak" });
    }
  });
}
