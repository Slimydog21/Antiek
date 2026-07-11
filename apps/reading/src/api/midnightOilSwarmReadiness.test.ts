import { describe, expect, it } from "vitest";
import {
  evaluateMidnightOilSwarmReadiness,
  formatSwarmReadinessSummary,
} from "./midnightOilSwarmReadiness";

describe("evaluateMidnightOilSwarmReadiness", () => {
  it("unattended_ready when all gates pass but never live", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 120,
      goal_count: 2,
      price_ceiling_usd: 5,
      recommended_ceiling_usd: 4,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(d.unattended_ready).toBe(true);
    expect(d.live_execution_authorized).toBe(false);
    expect(d.authority).toBe("midnight_oil_swarm_readiness_advisory");
  });

  it("null ceiling fail closed", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 60,
      goal_count: 1,
      price_ceiling_usd: null,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(d.ceiling_ready).toBe(false);
    expect(d.unattended_ready).toBe(false);
    expect(d.live_execution_authorized).toBe(false);
  });

  it("zero ceiling dry without spend consent", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 30,
      goal_count: 1,
      price_ceiling_usd: 0,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: false,
    });
    expect(d.consent_ready).toBe(true);
    expect(d.unattended_ready).toBe(true);
    expect(d.live_execution_authorized).toBe(false);
  });

  it("positive ceiling requires spend consent", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 60,
      goal_count: 1,
      price_ceiling_usd: 10,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: false,
    });
    expect(d.consent_ready).toBe(false);
    expect(d.unattended_ready).toBe(false);
  });

  it("requires unattended_ack", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 60,
      goal_count: 1,
      price_ceiling_usd: 5,
      brief_dispatch_ready: true,
      unattended_ack: false,
      spend_consent: true,
    });
    expect(d.unattended_ready).toBe(false);
    expect(d.live_execution_authorized).toBe(false);
  });

  it("requires brief_dispatch_ready", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 60,
      goal_count: 1,
      price_ceiling_usd: 5,
      brief_dispatch_ready: false,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(d.brief_ready).toBe(false);
    expect(d.unattended_ready).toBe(false);
  });

  it("rejects empty operator and non-positive minutes", () => {
    expect(() =>
      evaluateMidnightOilSwarmReadiness({
        operator_id: "  ",
        work_minutes: 10,
        goal_count: 1,
        price_ceiling_usd: 1,
        brief_dispatch_ready: true,
        unattended_ack: true,
        spend_consent: true,
      }),
    ).toThrow(/operator_id/);
    expect(() =>
      evaluateMidnightOilSwarmReadiness({
        operator_id: "op",
        work_minutes: 0,
        goal_count: 1,
        price_ceiling_usd: 1,
        brief_dispatch_ready: true,
        unattended_ack: true,
        spend_consent: true,
      }),
    ).toThrow(/work_minutes/);
  });
});

describe("formatSwarmReadinessSummary", () => {
  it("summarizes honesty", () => {
    const d = evaluateMidnightOilSwarmReadiness({
      operator_id: "op",
      work_minutes: 10,
      goal_count: 1,
      price_ceiling_usd: 0,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: false,
    });
    expect(formatSwarmReadinessSummary(d)).toMatch(
      /live_execution_authorized=false/,
    );
  });
});
