import { describe, expect, it } from "vitest";

import {
  emoteForExperience,
  emitWernerExperience,
  installReactionBus,
  type ProductExperience,
  WERNER_EXPERIENCE_EVENT,
} from "./reactionBus";
import type { EmoteKind } from "./emotes";
import type { WernerStageController } from "./WernerStage";

function fakeStage(): WernerStageController & { emotes: EmoteKind[] } {
  const emotes: EmoteKind[] = [];
  return {
    emotes,
    emote: (kind: EmoteKind) => {
      emotes.push(kind);
    },
    moveTo: () => {},
    waddleToEl: () => {},
    follow: () => {},
    idle: () => {},
    freeze: () => {},
    unfreeze: () => {},
    getState: () => ({ name: "idle" }) as ReturnType<WernerStageController["getState"]>,
    dispose: () => {},
  } as unknown as WernerStageController & { emotes: EmoteKind[] };
}

describe("emoteForExperience (shipped pure map)", () => {
  const cases: Array<[ProductExperience, string]> = [
    ["highlight", "curious"],
    ["deep_research_start", "thinking"],
    ["deep_research_complete", "happy"],
    ["deep_research_error", "dizzy"],
    ["fail", "dizzy"],
    ["error", "dizzy"],
    ["idle", "sleeping"],
  ];

  it.each(cases)("%s → %s", (experience, emote) => {
    expect(emoteForExperience(experience)).toBe(emote);
  });
});

describe("installReactionBus", () => {
  it("fires stage.emote from emitWernerExperience", () => {
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    emitWernerExperience({ experience: "highlight" });
    expect(stage.emotes).toEqual(["curious"]);
    teardown();
  });

  it("honours explicit emote override", () => {
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    emitWernerExperience({ experience: "idle", emote: "happy" });
    expect(stage.emotes).toEqual(["happy"]);
    teardown();
  });

  it("teardown stops reactions", () => {
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    teardown();
    emitWernerExperience({ experience: "fail" });
    expect(stage.emotes).toEqual([]);
  });

  it("listens on the shared event name", () => {
    expect(WERNER_EXPERIENCE_EVENT).toBe("antiek:werner-experience");
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    window.dispatchEvent(
      new CustomEvent(WERNER_EXPERIENCE_EVENT, {
        detail: { experience: "deep_research_start" },
      }),
    );
    expect(stage.emotes).toEqual(["thinking"]);
    teardown();
  });

  it("ignores malformed detail", () => {
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    window.dispatchEvent(new CustomEvent(WERNER_EXPERIENCE_EVENT, { detail: {} }));
    expect(stage.emotes).toEqual([]);
    teardown();
  });
});
