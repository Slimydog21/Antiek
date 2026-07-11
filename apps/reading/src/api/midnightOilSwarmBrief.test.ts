import { describe, expect, it } from "vitest";
import {
  buildMidnightOilSwarmBrief,
  formatSwarmBriefSummary,
} from "./midnightOilSwarmBrief";

const baseGoals = [
  { goal_id: "g1", statement: "Map arxiv scaling laws", priority: 2 },
  { goal_id: "g2", statement: "Contrast substack analysis", priority: 1 },
];

describe("buildMidnightOilSwarmBrief", () => {
  it("builds lanes with time shares and never authorizes live", () => {
    const b = buildMidnightOilSwarmBrief({
      operator_id: "op-1",
      work_minutes: 120,
      goals: baseGoals,
      price_ceiling_usd: 5,
      recommended_ceiling_usd: 4,
      operator_approved: true,
    });
    expect(b.lanes).toHaveLength(2);
    expect(b.lanes[0].time_share).toBeCloseTo(2 / 3);
    expect(b.lanes[1].time_share).toBeCloseTo(1 / 3);
    expect(b.dispatch_ready).toBe(true);
    expect(b.live_execution_authorized).toBe(false);
    expect(b.notes.some((n) => /live_execution_authorized=false/.test(n))).toBe(
      true,
    );
  });

  it("dispatch_ready false without approval", () => {
    const b = buildMidnightOilSwarmBrief({
      operator_id: "op-1",
      work_minutes: 60,
      goals: baseGoals,
      price_ceiling_usd: 5,
      operator_approved: false,
    });
    expect(b.dispatch_ready).toBe(false);
    expect(b.live_execution_authorized).toBe(false);
  });

  it("unknown ceiling keeps dispatch_ready false (no invent 0)", () => {
    const b = buildMidnightOilSwarmBrief({
      operator_id: "op-1",
      work_minutes: 60,
      goals: baseGoals,
      price_ceiling_usd: null,
      operator_approved: true,
    });
    expect(b.dispatch_ready).toBe(false);
    expect(b.price_ceiling_usd).toBeNull();
  });

  it("zero ceiling allows dry dispatch_ready", () => {
    const b = buildMidnightOilSwarmBrief({
      operator_id: "op-1",
      work_minutes: 30,
      goals: [baseGoals[0]],
      price_ceiling_usd: 0,
      operator_approved: true,
    });
    expect(b.dispatch_ready).toBe(true);
    expect(b.live_execution_authorized).toBe(false);
  });

  it("rejects empty goals and non-positive minutes", () => {
    expect(() =>
      buildMidnightOilSwarmBrief({
        operator_id: "op",
        work_minutes: 0,
        goals: baseGoals,
        price_ceiling_usd: 1,
        operator_approved: true,
      }),
    ).toThrow(/work_minutes/);
    expect(() =>
      buildMidnightOilSwarmBrief({
        operator_id: "op",
        work_minutes: 10,
        goals: [],
        price_ceiling_usd: 1,
        operator_approved: true,
      }),
    ).toThrow(/goals/);
  });

  it("rejects non-bool operator_approved", () => {
    expect(() =>
      buildMidnightOilSwarmBrief({
        operator_id: "op",
        work_minutes: 10,
        goals: baseGoals,
        price_ceiling_usd: 1,
        // @ts-expect-error intentional
        operator_approved: "true",
      }),
    ).toThrow(/operator_approved/);
  });

  it("rejects non-finite ceiling", () => {
    expect(() =>
      buildMidnightOilSwarmBrief({
        operator_id: "op",
        work_minutes: 10,
        goals: baseGoals,
        price_ceiling_usd: Number.NaN,
        operator_approved: true,
      }),
    ).toThrow(/finite/);
  });
});

describe("formatSwarmBriefSummary", () => {
  it("summarizes honesty", () => {
    const b = buildMidnightOilSwarmBrief({
      operator_id: "op",
      work_minutes: 10,
      goals: [baseGoals[0]],
      price_ceiling_usd: 1,
      operator_approved: true,
    });
    expect(formatSwarmBriefSummary(b)).toMatch(/live_execution_authorized=false/);
  });
});
