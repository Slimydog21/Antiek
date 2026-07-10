import { describe, expect, it } from "vitest";
import { promptCostEstimateReadiness } from "./promptCostEstimateReadiness";

describe("promptCostEstimateReadiness (avh)", () => {
  it("is estimate_ready with non-negative finite counts", () => {
    const r = promptCostEstimateReadiness({
      input_chars: 2000,
      expected_output_tokens: 500,
    });
    expect(r.estimate_ready).toBe(true);
    expect(r.block_reason).toBe("ok");
    expect(r.soft_budget).toBe(true);
    expect(r.never_invent_zero).toBe(true);
    expect(r.never_auto_route).toBe(true);
    expect(r.estimate_title).toMatch(/soft gate/i);
  });

  it("allows zero counts", () => {
    const r = promptCostEstimateReadiness({
      input_chars: 0,
      expected_output_tokens: 0,
    });
    expect(r.estimate_ready).toBe(true);
  });

  it("rejects negative or non-finite input", () => {
    expect(
      promptCostEstimateReadiness({
        input_chars: -1,
        expected_output_tokens: 10,
      }).block_reason,
    ).toBe("bad_input_chars");
    expect(
      promptCostEstimateReadiness({
        input_chars: 10,
        expected_output_tokens: Number.NaN,
      }).block_reason,
    ).toBe("bad_output_tokens");
    expect(promptCostEstimateReadiness({}).estimate_ready).toBe(false);
  });
});
