import type { EmoteKind } from "./emotes";
import type { WernerStageController } from "./WernerStage";

export const PRODUCT_EXPERIENCES = [
  "highlight",
  "deep_research_start",
  "deep_research_complete",
  "deep_research_error",
  "idle",
  "fail",
  "note_saved",
  "voice_recording_started",
  "voice_playback_started",
  "thought_partner_reply_received",
  "evidence_source_opened",
] as const;

export type ProductExperience = (typeof PRODUCT_EXPERIENCES)[number];

const REACTION_MAP: Readonly<Record<ProductExperience, EmoteKind>> = {
  highlight: "curious",
  deep_research_start: "thinking",
  deep_research_complete: "happy",
  deep_research_error: "dizzy",
  idle: "sleeping",
  fail: "dizzy",
  note_saved: "noted",
  voice_recording_started: "thinking",
  voice_playback_started: "thinking",
  thought_partner_reply_received: "happy",
  evidence_source_opened: "curious",
};

export const WERNER_EXPERIENCE_EVENT = "antiek:werner-experience";

export interface WernerExperienceDetail {
  experience: ProductExperience;
}

export function isProductExperience(
  value: unknown,
): value is ProductExperience {
  return (
    typeof value === "string" &&
    (PRODUCT_EXPERIENCES as readonly string[]).includes(value)
  );
}

export function emoteForExperience(experience: ProductExperience): EmoteKind {
  return REACTION_MAP[experience];
}

export function emitWernerExperience(experience: ProductExperience): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<WernerExperienceDetail>(WERNER_EXPERIENCE_EVENT, {
      detail: { experience },
    }),
  );
}

export interface ReactionBusOptions {
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
}

export function installReactionBus(
  stage: Pick<WernerStageController, "emote">,
  options: ReactionBusOptions = {},
): () => void {
  const target =
    options.target ?? (typeof window !== "undefined" ? window : null);
  if (!target) return () => {};

  const onExperience = (event: Event) => {
    const experience = (event as CustomEvent<Partial<WernerExperienceDetail>>)
      .detail?.experience;
    if (!isProductExperience(experience)) return;
    stage.emote(emoteForExperience(experience));
  };

  target.addEventListener(
    WERNER_EXPERIENCE_EVENT,
    onExperience as EventListener,
  );
  return () =>
    target.removeEventListener(
      WERNER_EXPERIENCE_EVENT,
      onExperience as EventListener,
    );
}
