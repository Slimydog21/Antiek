import { describe, expect, it } from "vitest";

import {
  installReactionBus,
  WERNER_EXPERIENCE_EVENT,
  type ProductExperience,
} from "./reactionBus";
import type { EmoteKind } from "./emotes";
import type { WernerStageController } from "./WernerStage";
import {
  notifyPointerIdleEdge,
  notifyShellFailure,
} from "./shellExperienceSignals";

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
    getState: () =>
      ({ name: "idle" }) as ReturnType<WernerStageController["getState"]>,
    dispose: () => {},
  } as unknown as WernerStageController & { emotes: EmoteKind[] };
}

describe("shellExperienceSignals (product call sites)", () => {
  it("notifyPointerIdleEdge emits idle only on false→true edge", () => {
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    expect(notifyPointerIdleEdge(false, false)).toBe(false);
    expect(notifyPointerIdleEdge(true, true)).toBe(false);
    expect(notifyPointerIdleEdge(true, false)).toBe(false);
    expect(notifyPointerIdleEdge(false, true)).toBe(true);
    expect(stage.emotes).toEqual(["sleeping"]);
    teardown();
  });

  it("notifyShellFailure emits fail → dizzy", () => {
    const stage = fakeStage();
    const teardown = installReactionBus(stage);
    expect(notifyShellFailure("network")).toBe(true);
    expect(stage.emotes).toEqual(["dizzy"]);
    teardown();
  });

  it("dispatches the shared experience event with product experiences", () => {
    const seen: ProductExperience[] = [];
    const on = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, on);
    notifyPointerIdleEdge(false, true);
    notifyShellFailure("x");
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, on);
    expect(seen).toEqual(["idle", "fail"]);
  });
});
