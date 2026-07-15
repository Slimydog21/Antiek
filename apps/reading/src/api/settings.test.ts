import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import {
  fetchModelDecision,
  isModelDecisionResponse,
  type ModelDecisionResponse,
} from "./settings";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

const validDecision: ModelDecisionResponse = {
  authority: "advisory",
  task: "deep_research",
  recommended_tier: null,
  recommendation_status: "insufficient_measured_evidence",
  benchmark_status: "unavailable",
  benchmark_generated_at: null,
  benchmark_measured_candidates: 0,
  benchmark_operational_candidates: 0,
  candidates: [],
  notes: ["No current report."],
};

describe("model decision response decoding", () => {
  beforeEach(() => vi.clearAllMocks());

  it("accepts the complete advisory response contract", () => {
    expect(isModelDecisionResponse(validDecision)).toBe(true);
  });

  it.each([
    { ...validDecision, candidates: undefined },
    { ...validDecision, notes: [42] },
    { ...validDecision, benchmark_status: "invented" },
    { ...validDecision, benchmark_measured_candidates: Number.NaN },
  ])("rejects malformed evidence before it reaches Settings: %o", (payload) => {
    expect(isModelDecisionResponse(payload)).toBe(false);
  });

  it("rejects a malformed successful HTTP response", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(
      new Response(JSON.stringify({
        authority: "advisory",
        task: "deep_research",
      }), { status: 200 }),
    );

    await expect(fetchModelDecision({
      task: "deep_research",
      input_chars: 2_000,
      expected_output_tokens: 500,
    })).rejects.toThrow("invalid model-decision response");
  });
});
