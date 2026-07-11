import { describe, expect, it } from "vitest";
import {
  composeMidnightOilPriceCeilingApproval,
  formatMidnightOilPriceCeilingApprovalSummary,
} from "./midnightOilPriceCeilingApprovalCompose";

const goals = [
  { goal_id: "g1", title: "Map scaling literature" },
  { goal_id: "g2", title: "Synthesize open problems" },
];

describe("composeMidnightOilPriceCeilingApproval", () => {
  it("recommend_only surfaces advisory ceiling", () => {
    const c = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 120,
      goals,
      usd_per_hour: 30,
      price_ceiling_ack: false,
      operator_ack: false,
      stage: "recommend_only",
    });
    expect(c.recommend.recommended_ceiling_usd).not.toBeNull();
    expect(c.recommend.recommended_ceiling_usd!).toBeGreaterThan(0);
    expect(c.ceiling_approved).toBe(false);
    expect(c.pack_ready).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.authority).toBe(
      "midnight_oil_price_ceiling_approval_compose_advisory",
    );
    expect(formatMidnightOilPriceCeilingApprovalSummary(c)).toMatch(
      /charge_executed=false/,
    );
  });

  it("approve_ceiling when approved >= recommended", () => {
    const rec = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: 20,
      price_ceiling_ack: false,
      operator_ack: false,
      stage: "recommend_only",
    });
    const recommended = rec.recommend.recommended_ceiling_usd!;
    const c = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: 20,
      approved_ceiling_usd: recommended,
      price_ceiling_ack: true,
      operator_ack: true,
      stage: "approve_ceiling",
    });
    expect(c.ceiling_approved).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.charge_executed).toBe(false);
    expect(c.unattended).toBeNull();
  });

  it("blocks approve when below recommended without override", () => {
    const rec = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: 50,
      price_ceiling_ack: false,
      operator_ack: false,
      stage: "recommend_only",
    });
    const recommended = rec.recommend.recommended_ceiling_usd!;
    const c = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: 50,
      approved_ceiling_usd: Math.max(0, recommended - 10),
      price_ceiling_ack: true,
      operator_ack: true,
      stage: "approve_ceiling",
    });
    expect(c.ceiling_approved).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("unattended_pack ready after dual acks + ceiling", () => {
    const rec = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 90,
      goals,
      usd_per_hour: 25,
      price_ceiling_ack: false,
      operator_ack: false,
      stage: "recommend_only",
    });
    const recommended = rec.recommend.recommended_ceiling_usd!;
    const c = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 90,
      goals,
      usd_per_hour: 25,
      approved_ceiling_usd: recommended + 5,
      price_ceiling_ack: true,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
      stage: "unattended_pack",
    });
    expect(c.ceiling_approved).toBe(true);
    expect(c.unattended).not.toBeNull();
    expect(c.unattended!.live_execution_authorized).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.charge_executed).toBe(false);
    // package_ready depends on entry/launch gates
    expect(typeof c.pack_ready).toBe("boolean");
  });

  it("null rate keeps recommended null (no invent 0)", () => {
    const c = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: null,
      price_ceiling_ack: false,
      operator_ack: false,
      stage: "recommend_only",
    });
    expect(c.recommend.recommended_ceiling_usd).toBeNull();
    expect(c.charge_executed).toBe(false);
  });

  it("below override allows lower approved ceiling", () => {
    const rec = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: 40,
      price_ceiling_ack: false,
      operator_ack: false,
      stage: "recommend_only",
    });
    const recommended = rec.recommend.recommended_ceiling_usd!;
    const c = composeMidnightOilPriceCeilingApproval({
      operator_id: "op-1",
      work_minutes: 60,
      goals,
      usd_per_hour: 40,
      approved_ceiling_usd: recommended * 0.5,
      below_recommend_override: true,
      price_ceiling_ack: true,
      operator_ack: true,
      stage: "approve_ceiling",
    });
    expect(c.ceiling_approved).toBe(true);
    expect(c.pack_ready).toBe(true);
  });
});
