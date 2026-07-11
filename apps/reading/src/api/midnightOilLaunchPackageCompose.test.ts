import { describe, expect, it } from "vitest";
import {
  composeMidnightOilLaunchPackage,
  formatMidnightOilLaunchPackageSummary,
  recommendMidnightOilPriceCeiling,
} from "./midnightOilLaunchPackageCompose";

const goals = [
  { goal_id: "g1", statement: "Map arxiv scaling", priority: 2 },
  { goal_id: "g2", statement: "Substack contrast", priority: 1 },
];

describe("recommendMidnightOilPriceCeiling", () => {
  it("returns null when rate unknown (no invent 0)", () => {
    const r = recommendMidnightOilPriceCeiling({
      work_minutes: 60,
      goal_count: 2,
      usd_per_hour: null,
    });
    expect(r.recommended_ceiling_usd).toBeNull();
    expect(r.notes.some((n) => n.includes("no invent"))).toBe(true);
  });

  it("computes finite recommended from rate", () => {
    const r = recommendMidnightOilPriceCeiling({
      work_minutes: 60,
      goal_count: 1,
      usd_per_hour: 10,
    });
    expect(r.recommended_ceiling_usd).toBe(10);
    expect(r.work_hours).toBe(1);
  });

  it("rejects non-positive minutes", () => {
    expect(() =>
      recommendMidnightOilPriceCeiling({
        work_minutes: 0,
        goal_count: 1,
        usd_per_hour: 1,
      }),
    ).toThrow(/work_minutes/);
  });
});

describe("composeMidnightOilLaunchPackage", () => {
  it("package ready without live execution", () => {
    const p = composeMidnightOilLaunchPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      price_ceiling_usd: 15,
      usd_per_hour: 10,
      operator_approved: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(p.live_execution_authorized).toBe(false);
    expect(p.brief.live_execution_authorized).toBe(false);
    expect(p.readiness.live_execution_authorized).toBe(false);
    expect(p.package_ready).toBe(true);
    expect(p.brief.dispatch_ready).toBe(true);
    expect(p.readiness.unattended_ready).toBe(true);
    expect(p.recommend.recommended_ceiling_usd).not.toBeNull();
    expect(p.authority).toBe("midnight_oil_launch_package_compose_advisory");
    expect(formatMidnightOilLaunchPackageSummary(p)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("not ready without ack or consent", () => {
    const p = composeMidnightOilLaunchPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      price_ceiling_usd: 10,
      recommended_ceiling_usd: 8,
      operator_approved: true,
      unattended_ack: false,
      spend_consent: true,
    });
    expect(p.package_ready).toBe(false);
    expect(p.live_execution_authorized).toBe(false);

    const noConsent = composeMidnightOilLaunchPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      price_ceiling_usd: 10,
      recommended_ceiling_usd: 8,
      operator_approved: true,
      unattended_ack: true,
      spend_consent: false,
    });
    expect(noConsent.package_ready).toBe(false);
    expect(noConsent.live_execution_authorized).toBe(false);
  });

  it("zero ceiling dry plan can be package ready", () => {
    const p = composeMidnightOilLaunchPackage({
      operator_id: "op-1",
      work_minutes: 30,
      goals: [goals[0]],
      price_ceiling_usd: 0,
      recommended_ceiling_usd: 0,
      operator_approved: true,
      unattended_ack: true,
      spend_consent: false,
    });
    expect(p.package_ready).toBe(true);
    expect(p.live_execution_authorized).toBe(false);
    expect(p.readiness.consent_ready).toBe(true);
  });

  it("unknown rate yields null recommended and still packages", () => {
    const p = composeMidnightOilLaunchPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      price_ceiling_usd: 5,
      usd_per_hour: null,
      operator_approved: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(p.recommend.recommended_ceiling_usd).toBeNull();
    expect(p.live_execution_authorized).toBe(false);
    expect(p.package_ready).toBe(true);
  });

  it("rejects empty goals", () => {
    expect(() =>
      composeMidnightOilLaunchPackage({
        operator_id: "op-1",
        work_minutes: 60,
        goals: [],
        price_ceiling_usd: 1,
        operator_approved: false,
        unattended_ack: false,
        spend_consent: false,
      }),
    ).toThrow(/goals/);
  });
});
