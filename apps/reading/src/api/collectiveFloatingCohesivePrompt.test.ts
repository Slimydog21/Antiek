import { describe, expect, it } from "vitest";
import {
  buildCollectiveFloatingCohesivePrompt,
  formatCohesivePromptSummary,
} from "./collectiveFloatingCohesivePrompt";

const base = [
  {
    instance_id: "fdr_1",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    highlight: "scaling laws",
    context: ["arxiv:1234 finding"],
  },
  {
    instance_id: "fdr_2",
    parent_asset_id: "asset-1",
    status: "open" as const,
    prior_prompt: "contrast substack claims",
  },
];

describe("buildCollectiveFloatingCohesivePrompt", () => {
  it("builds pack intent without live dispatch", () => {
    const intent = buildCollectiveFloatingCohesivePrompt(base, {
      cohesive_prompt: "Synthesize both lanes into one research question set",
      operator_ack: true,
    });
    expect(intent.live_dispatched).toBe(false);
    expect(intent.pack_ready).toBe(true);
    expect(intent.member_count).toBe(2);
    expect(intent.instance_ids).toEqual(["fdr_1", "fdr_2"]);
    expect(intent.context_cards.length).toBeGreaterThanOrEqual(2);
    expect(intent.authority).toBe(
      "collective_floating_cohesive_prompt_advisory",
    );
    expect(formatCohesivePromptSummary(intent)).toMatch(/live_dispatched=false/);
  });

  it("pack_ready false without operator_ack", () => {
    const intent = buildCollectiveFloatingCohesivePrompt(base, {
      cohesive_prompt: "Continue as one unit",
      operator_ack: false,
    });
    expect(intent.pack_ready).toBe(false);
    expect(intent.live_dispatched).toBe(false);
    expect(intent.notes.some((n) => n.includes("pack_ready=false"))).toBe(
      true,
    );
  });

  it("requires ≥2 same parent distinct ids", () => {
    expect(() =>
      buildCollectiveFloatingCohesivePrompt([base[0]], {
        cohesive_prompt: "x",
        operator_ack: false,
      }),
    ).toThrow(/at least 2/);
    expect(() =>
      buildCollectiveFloatingCohesivePrompt(
        [base[0], { ...base[1], parent_asset_id: "other" }],
        { cohesive_prompt: "x", operator_ack: false },
      ),
    ).toThrow(/same parent/);
    expect(() =>
      buildCollectiveFloatingCohesivePrompt(
        [base[0], { ...base[0] }],
        { cohesive_prompt: "x", operator_ack: false },
      ),
    ).toThrow(/distinct/);
  });

  it("rejects closed members and blank prompt", () => {
    expect(() =>
      buildCollectiveFloatingCohesivePrompt(
        [base[0], { ...base[1], status: "closed" }],
        { cohesive_prompt: "ok", operator_ack: false },
      ),
    ).toThrow(/not closed/);
    expect(() =>
      buildCollectiveFloatingCohesivePrompt(base, {
        cohesive_prompt: "   ",
        operator_ack: false,
      }),
    ).toThrow(/cohesive_prompt/);
  });

  it("never invents context when none supplied", () => {
    const intent = buildCollectiveFloatingCohesivePrompt(
      [
        {
          instance_id: "a",
          parent_asset_id: "p",
          status: "completed",
        },
        {
          instance_id: "b",
          parent_asset_id: "p",
          status: "completed",
        },
      ],
      { cohesive_prompt: "Ask both agents the same critique", operator_ack: true },
    );
    expect(intent.context_cards).toEqual([]);
    expect(
      intent.notes.some((n) => n.includes("no invent content")),
    ).toBe(true);
    expect(intent.live_dispatched).toBe(false);
  });

  it("accepts extra_context and hardcodes live_dispatched false", () => {
    const intent = buildCollectiveFloatingCohesivePrompt(base, {
      cohesive_prompt: "Cross-examine",
      operator_ack: true,
      extra_context: ["operator note: prioritize citations"],
    });
    expect(intent.context_cards).toContain(
      "operator note: prioritize citations",
    );
    expect(intent.live_dispatched).toBe(false);
    // structural honesty: field is literal false type-level + runtime
    expect(Object.isFrozen(intent) || intent.live_dispatched === false).toBe(
      true,
    );
  });
});
