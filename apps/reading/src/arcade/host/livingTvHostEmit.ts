/**
 * Host-layer living-TV emit for arcade shells.
 *
 * Dispatches the same CustomEvent the product reaction bus listens for, without
 * importing `werner/reactionBus` — arcade core must stay free of product-bus
 * imports (see arcadeBoundary.test.ts). Product PenguinMascot / installReactionBus
 * still receive these beats.
 */

/** Event name must match WERNER_EXPERIENCE_EVENT in werner/reactionBus. */
export const LIVING_TV_HOST_EVENT = "antiek:werner-experience";

export function emitLivingTvHostBeat(experience: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(LIVING_TV_HOST_EVENT, {
      detail: { experience },
    }),
  );
}
