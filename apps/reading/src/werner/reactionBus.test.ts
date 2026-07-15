import { afterEach, describe, expect, it, vi } from "vitest";

import {
  emoteForExperience,
  emitWernerExperience,
  installReactionBus,
  isProductExperience,
  PRODUCT_EXPERIENCES,
  WERNER_EXPERIENCE_EVENT,
  type ProductExperience,
} from "./reactionBus";

afterEach(() => vi.restoreAllMocks());

describe("Werner product reaction bus", () => {
  const cases: Array<[ProductExperience, string]> = [
    ["highlight", "curious"],
    ["deep_research_start", "thinking"],
    ["deep_research_complete", "happy"],
    ["deep_research_error", "dizzy"],
    ["source_read_committed", "happy"],
    ["outline_block_committed", "curious"],
    ["speak_invite_committed", "happy"],
    ["model_evidence_compared", "curious"],
    ["fail", "dizzy"],
  ];

  it.each(cases)("maps %s to %s", (experience, emote) => {
    expect(emoteForExperience(experience)).toBe(emote);
  });

  it("keeps the runtime allowlist and exhaustive map aligned", () => {
    expect(PRODUCT_EXPERIENCES).toHaveLength(cases.length);
    expect(PRODUCT_EXPERIENCES.every(isProductExperience)).toBe(true);
    expect(isProductExperience("recording_started")).toBe(false);
  });

  it("translates a valid event once and teardown removes the listener", () => {
    const emote = vi.fn();
    const teardown = installReactionBus({ emote });

    emitWernerExperience("highlight");
    expect(emote).toHaveBeenCalledTimes(1);
    expect(emote).toHaveBeenLastCalledWith("curious");

    teardown();
    emitWernerExperience("fail");
    expect(emote).toHaveBeenCalledTimes(1);
  });

  it("ignores missing and unknown runtime detail", () => {
    const emote = vi.fn();
    const teardown = installReactionBus({ emote });

    window.dispatchEvent(new CustomEvent(WERNER_EXPERIENCE_EVENT));
    window.dispatchEvent(
      new CustomEvent(WERNER_EXPERIENCE_EVENT, {
        detail: { experience: "arbitrary_plugin_event" },
      }),
    );

    expect(emote).not.toHaveBeenCalled();
    teardown();
  });
});
