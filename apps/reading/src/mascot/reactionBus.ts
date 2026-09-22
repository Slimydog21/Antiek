import type { EmoteKind } from "./emotes";
import type { MascotStageController } from "./MascotStage";

export const PRODUCT_EXPERIENCES = [
  "highlight",
  "deep_research_start",
  "deep_research_complete",
  "deep_research_error",
  "evidence_source_opened",
  "idle",
  "fail",
] as const;

export type ProductExperience = (typeof PRODUCT_EXPERIENCES)[number];

const REACTION_MAP: Readonly<Record<ProductExperience, EmoteKind>> = {
  highlight: "curious",
  deep_research_start: "thinking",
  deep_research_complete: "happy",
  deep_research_error: "dizzy",
  evidence_source_opened: "curious",
  idle: "sleeping",
  fail: "dizzy",
};

export const MASCOT_EXPERIENCE_EVENT = "antiek:mascot-experience";

export interface MascotExperienceDetail {
  experience: ProductExperience;
}

export function isProductExperience(value: unknown): value is ProductExperience {
  return (
    typeof value === "string" &&
    (PRODUCT_EXPERIENCES as readonly string[]).includes(value)
  );
}

export function emoteForExperience(experience: ProductExperience): EmoteKind {
  return REACTION_MAP[experience];
}

export function emitMascotExperience(experience: ProductExperience): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<MascotExperienceDetail>(MASCOT_EXPERIENCE_EVENT, {
      detail: { experience },
    }),
  );
}

export interface ReactionBusOptions {
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
}

export function installReactionBus(
  stage: Pick<MascotStageController, "emote">,
  options: ReactionBusOptions = {},
): () => void {
  const target =
    options.target ?? (typeof window !== "undefined" ? window : null);
  if (!target) return () => {};

  const onExperience = (event: Event) => {
    const experience = (event as CustomEvent<Partial<MascotExperienceDetail>>)
      .detail?.experience;
    if (!isProductExperience(experience)) return;
    stage.emote(emoteForExperience(experience));
  };

  target.addEventListener(
    MASCOT_EXPERIENCE_EVENT,
    onExperience as EventListener,
  );
  return () =>
    target.removeEventListener(
      MASCOT_EXPERIENCE_EVENT,
      onExperience as EventListener,
    );
}
