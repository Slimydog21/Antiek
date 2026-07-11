import { describe, expect, it } from "vitest";
import {
  composeDeepResearchQualityBudgetGate,
  formatDeepResearchQualityBudgetGateSummary,
} from "./deepResearchQualityBudgetGateCompose";

describe("composeDeepResearchQualityBudgetGate", () => {
  it("opens gate when quality and budget pass", () => {
    const c = composeDeepResearchQualityBudgetGate({
      session_id: "dr-1",
      quality_overall: 0.82,
      quality_floor: 0.5,
      would_exceed: false,
      citation_pack_ready: true,
      operator_ack: true,
    });
    expect(c.gate_ready).toBe(true);
    expect(c.quality_ready).toBe(true);
    expect(c.budget_ready).toBe(true);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(formatDeepResearchQualityBudgetGateSummary(c)).toMatch(
      /live_dispatch_authorized=false/,
    );
  });

  it("fails closed on low quality and unknown budget", () => {
    const low = composeDeepResearchQualityBudgetGate({
      session_id: "dr",
      quality_overall: 0.2,
      quality_floor: 0.5,
      would_exceed: false,
      operator_ack: true,
    });
    expect(low.quality_ready).toBe(false);
    expect(low.gate_ready).toBe(false);

    const unk = composeDeepResearchQualityBudgetGate({
      session_id: "dr",
      quality_overall: 0.9,
      would_exceed: null,
      operator_ack: true,
    });
    expect(unk.budget_ready).toBe(false);
    expect(unk.gate_ready).toBe(false);
    expect(unk.live_dispatch_authorized).toBe(false);
  });
});
