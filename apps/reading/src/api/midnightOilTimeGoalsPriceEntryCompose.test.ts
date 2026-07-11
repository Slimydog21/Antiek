import { describe, expect, it } from "vitest";
import {
  composeMidnightOilTimeGoalsPriceEntry,
  formatMidnightOilTimeGoalsPriceEntrySummary,
} from "./midnightOilTimeGoalsPriceEntryCompose";

describe("composeMidnightOilTimeGoalsPriceEntry", () => {
  it("entry ready when goals, ack, and approved ceiling", () => {
    const c = composeMidnightOilTimeGoalsPriceEntry({
      operator_id: "op-1",
      work_minutes: 120,
      goals: [
        { goal_id: "g1", title: "Survey arxiv" },
        { goal_id: "g2", title: "Draft notes" },
      ],
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: true,
    });
    expect(c.entry_ready).toBe(true);
    expect(c.goal_count).toBe(2);
    expect(c.recommend.recommended_ceiling_usd).not.toBeNull();
    expect(c.live_execution_authorized).toBe(false);
    expect(formatMidnightOilTimeGoalsPriceEntrySummary(c)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("not ready without approved ceiling when rec known", () => {
    const c = composeMidnightOilTimeGoalsPriceEntry({
      operator_id: "op",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: null,
      operator_ack: true,
    });
    expect(c.entry_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("rejects empty goals", () => {
    expect(() =>
      composeMidnightOilTimeGoalsPriceEntry({
        operator_id: "op",
        work_minutes: 30,
        goals: [],
        operator_ack: true,
      }),
    ).toThrow(/goals/);
  });
});
