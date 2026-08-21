/**
 * Werner product-experience reaction bus.
 *
 * Maps named product experiences onto the existing emote vocabulary so the
 * single PenguinMascot / WernerStage owner can react to shell events without
 * forking a second penguin.
 *
 * Events are CustomEvents on `window` (same pattern as PRODUCT_ACTIVATE). The
 * pure mapping lives in `emoteForExperience` so unit tests drive the shipped
 * function without a DOM.
 */

import type { EmoteKind } from "./emotes";
import type { WernerStageController } from "./WernerStage";

/** Named product experiences the shell (or any feature) may announce. */
export type ProductExperience =
  | "highlight"
  | "deep_research_start"
  | "deep_research_complete"
  | "deep_research_error"
  | "idle"
  | "fail"
  | "error";

export const WERNER_EXPERIENCE_EVENT = "antiek:werner-experience";

export interface WernerExperienceDetail {
  experience: ProductExperience;
  /** Optional override emote; defaults to the map below. */
  emote?: EmoteKind;
}

/**
 * Pure reaction map — the contract tests pin. Keep this small and hard to vary:
 * every experience has exactly one default emote.
 */
export function emoteForExperience(experience: ProductExperience): EmoteKind {
  switch (experience) {
    case "highlight":
      return "curious";
    case "deep_research_start":
      return "thinking";
    case "deep_research_complete":
      return "happy";
    case "deep_research_error":
    case "fail":
    case "error":
      return "dizzy";
    case "idle":
      return "sleeping";
    default: {
      const _exhaustive: never = experience;
      return _exhaustive;
    }
  }
}

/** Emit a product experience for the living mascot (and any other listeners). */
export function emitWernerExperience(detail: WernerExperienceDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<WernerExperienceDetail>(WERNER_EXPERIENCE_EVENT, {
      detail,
    }),
  );
}

export interface ReactionBusOptions {
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
}

/**
 * Wire experience → stage.emote. Returns teardown. The stage owns interruption
 * (latest-wins); this listener only translates and fires.
 */
export function installReactionBus(
  stage: WernerStageController,
  options: ReactionBusOptions = {},
): () => void {
  const win = options.target ?? (typeof window !== "undefined" ? window : null);
  if (!win) return () => {};

  const onExperience = (event: Event) => {
    const detail = (event as CustomEvent<WernerExperienceDetail>).detail;
    if (!detail || !detail.experience) return;
    const kind = detail.emote ?? emoteForExperience(detail.experience);
    stage.emote(kind);
  };

  win.addEventListener(WERNER_EXPERIENCE_EVENT, onExperience as EventListener);
  return () => {
    win.removeEventListener(
      WERNER_EXPERIENCE_EVENT,
      onExperience as EventListener,
    );
  };
}
