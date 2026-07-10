import { describe, expect, it } from "vitest";
import {
  KNOWLEDGE_DENSE_PUBLICATION_PRESETS,
  knowledgeDensePresetById,
  knowledgeDensePresetCount,
} from "./knowledgeDensePresets";

describe("knowledgeDensePresets (auj)", () => {
  it("ships closed arxiv/substack/url connectors without auto-hydrate authority", () => {
    expect(knowledgeDensePresetCount()).toBeGreaterThanOrEqual(12);
    expect(KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length).toBe(
      knowledgeDensePresetCount(),
    );
    expect(
      KNOWLEDGE_DENSE_PUBLICATION_PRESETS.some((p) => p.id === "self-consistency"),
    ).toBe(true);
    expect(
      KNOWLEDGE_DENSE_PUBLICATION_PRESETS.some((p) => p.kind === "arxiv"),
    ).toBe(true);
    expect(
      KNOWLEDGE_DENSE_PUBLICATION_PRESETS.some((p) => p.kind === "substack"),
    ).toBe(true);
  });

  it("looks up by id without inventing missing presets", () => {
    const sc = knowledgeDensePresetById("self-consistency");
    expect(sc?.reference).toBe("arxiv:2203.11171");
    expect(sc?.kind).toBe("arxiv");
    expect(knowledgeDensePresetById("not-a-real-preset")).toBeNull();
    expect(knowledgeDensePresetById("")).toBeNull();
    expect(knowledgeDensePresetById(null)).toBeNull();
  });
});
