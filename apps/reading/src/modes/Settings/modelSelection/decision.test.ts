import { describe, expect, it } from "vitest";

import {
  buildBudgetBar,
  composeSelectionDecision,
  projectPromptCost,
  rankModelsForTask,
} from "./decision";

const models = [
  { modelId: "m-b", provider: "x", apiKeyId: "k1", label: "B" },
  { modelId: "m-a", provider: "x", apiKeyId: "k1", label: "A" },
  { modelId: "m-c", provider: "y", apiKeyId: "k2", label: "C" },
];

describe("rankModelsForTask", () => {
  it("sorts by score desc then modelId, preserves all models", () => {
    const ranked = rankModelsForTask("research_synth", models, [
      { modelId: "m-b", taskId: "research_synth", score: 0.9 },
      { modelId: "m-a", taskId: "research_synth", score: 0.9 },
      { modelId: "m-c", taskId: "other", score: 1 },
    ]);
    expect(ranked.map((r) => r.modelId)).toEqual(["m-a", "m-b", "m-c"]);
    expect(ranked[2]?.score).toBe(0);
  });
});

describe("buildBudgetBar", () => {
  it("ratio is null when limit is 0 (unconfigured)", () => {
    expect(
      buildBudgetBar({ apiKeyId: "k", usedCents: 10, limitCents: 0 }),
    ).toEqual({
      apiKeyId: "k",
      usedCents: 10,
      limitCents: 0,
      ratio: null,
    });
  });

  it("computes ratio when limit set", () => {
    expect(
      buildBudgetBar({ apiKeyId: "k", usedCents: 25, limitCents: 100 }),
    ).toMatchObject({ ratio: 0.25 });
  });
});

describe("projectPromptCost", () => {
  it("returns null without estimate", () => {
    expect(
      projectPromptCost(
        { apiKeyId: "k", usedCents: 0, limitCents: 100 },
        null,
      ),
    ).toBeNull();
  });

  it("flags wouldExceed without removing models", () => {
    const proj = projectPromptCost(
      { apiKeyId: "k", usedCents: 90, limitCents: 100 },
      {
        apiKeyId: "k",
        modelId: "m-a",
        estimatedTokens: 10_000,
        centsPer1kTokens: 2,
      },
    );
    expect(proj?.projectedCents).toBe(20);
    expect(proj?.wouldExceed).toBe(true);
    expect(proj?.postProjectionUsedCents).toBe(110);
  });
});

describe("composeSelectionDecision", () => {
  it("is pure, advisory, and order-preserving", () => {
    const input = {
      taskId: "research_synth",
      models,
      benchScores: [
        { modelId: "m-b", taskId: "research_synth", score: 0.8 },
        { modelId: "m-a", taskId: "research_synth", score: 0.95 },
      ],
      usage: { apiKeyId: "k1", usedCents: 40, limitCents: 100 },
      projectionRequest: {
        apiKeyId: "k1",
        modelId: "m-a",
        estimatedTokens: 5_000,
        centsPer1kTokens: 1,
      },
    };
    const a = composeSelectionDecision(input);
    const b = composeSelectionDecision(input);
    expect(a).toEqual(b);
    expect(a.authority).toBe("advisory");
    expect(a.recommendation[0]?.modelId).toBe("m-a");
    expect(a.budgetBar?.ratio).toBe(0.4);
    expect(a.projection?.wouldExceed).toBe(false);
    expect(a.projection?.projectedCents).toBe(5);
  });
});
