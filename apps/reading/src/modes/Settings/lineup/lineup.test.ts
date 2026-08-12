import { describe, expect, it } from "vitest";
import { GENERAL_SLOTS } from "./inventory";
import {
  benchCards,
  emptyLineup,
  occupant,
  resolveAction,
  substitute,
  substituteAdvanced,
  type LineupCard,
} from "./lineup";

const cards: LineupCard[] = [
  { id: "card-writer", displayName: "Sol", modelId: "gpt-5.6-sol", provider: "openai" },
  { id: "card-miner", displayName: "Luna", modelId: "gpt-5.6-luna", provider: "openai" },
  { id: "card-refine", displayName: "Sonnet", modelId: "claude-sonnet-5", provider: "anthropic" },
  { id: "card-verify", displayName: "Terra", modelId: "gpt-5.6-terra", provider: "openai" },
  { id: "card-bench", displayName: "Haiku", modelId: "claude-haiku-4-5", provider: "anthropic" },
];

describe("substitute", () => {
  it("puts a bench card into each of the four named general slots", () => {
    const incoming = [
      ["writer", "card-writer"],
      ["data miner", "card-miner"],
      ["data refinement", "card-refine"],
      ["data verification", "card-verify"],
    ] as const;

    let state = emptyLineup();
    for (const [slot, cardId] of incoming) {
      state = substitute(state, slot, cardId, cards);
      expect(occupant(state, slot, cards)?.id).toBe(cardId);
    }

    expect(GENERAL_SLOTS).toEqual([
      "writer",
      "data miner",
      "data refinement",
      "data verification",
    ]);
    expect(benchCards(state, cards).map((card) => card.id)).toEqual(["card-bench"]);
  });

  it("swaps two starters when a starter is substituted into another slot", () => {
    let state = emptyLineup();
    state = substitute(state, "writer", "card-writer", cards);
    state = substitute(state, "data miner", "card-miner", cards);
    state = substitute(state, "writer", "card-miner", cards);
    expect(occupant(state, "writer", cards)?.id).toBe("card-miner");
    expect(occupant(state, "data miner", cards)?.id).toBe("card-writer");
  });

  it("returns the previous starter to the bench when a bench card comes on", () => {
    let state = emptyLineup();
    state = substitute(state, "writer", "card-writer", cards);
    state = substitute(state, "writer", "card-bench", cards);
    expect(occupant(state, "writer", cards)?.id).toBe("card-bench");
    expect(benchCards(state, cards).map((card) => card.id)).toContain("card-writer");
  });
});

describe("override resolution", () => {
  it("lets an advanced pin win for one action while the sibling stays on the general starter", () => {
    let state = emptyLineup();
    state = substitute(state, "writer", "card-writer", cards);
    state = substituteAdvanced(state, "synthesizer", "card-bench", cards);

    expect(resolveAction(state, "synthesizer", cards)?.id).toBe("card-bench");
    expect(resolveAction(state, "creative_writer", cards)?.id).toBe("card-writer");
  });

  it("leaves an un-pinned extra unresolved even when general slots are filled", () => {
    let state = emptyLineup();
    state = substitute(state, "writer", "card-writer", cards);
    expect(resolveAction(state, "thought_partner", cards)).toBeNull();
    state = substituteAdvanced(state, "thought_partner", "card-refine", cards);
    expect(resolveAction(state, "thought_partner", cards)?.id).toBe("card-refine");
  });
});
