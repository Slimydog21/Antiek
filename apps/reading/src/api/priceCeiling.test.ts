import { describe, expect, it } from "vitest";
import {
  formatCeilingUsd,
  PriceCeilingError,
  recommendPriceCeiling,
} from "./priceCeiling";

describe("recommendPriceCeiling", () => {
  it("recommends advisory finite ceiling", () => {
    const rec = recommendPriceCeiling({
      hours: 2,
      goals: ["a", "b"],
      usd_per_hour_low: 1,
      usd_per_hour_high: 3,
      usd_per_goal: 0.5,
      contingency_fraction: 0.1,
    });
    expect(rec.authority).toBe("advisory");
    expect(rec.goal_count).toBe(2);
    expect(rec.low_usd).toBe(3);
    expect(rec.high_usd).toBe(7);
    expect(rec.recommended_ceiling_usd).toBeCloseTo(5.5);
  });

  it("rejects nonpositive hours", () => {
    expect(() => recommendPriceCeiling({ hours: 0, goals: 1 })).toThrow(
      PriceCeilingError,
    );
  });

  it("rejects overflow non-finite results", () => {
    expect(() =>
      recommendPriceCeiling({
        hours: 1e308,
        goals: 0,
        usd_per_hour_low: 1,
        usd_per_hour_high: 5,
      }),
    ).toThrow(/non-finite|overflow/i);
  });

  it("formatCeilingUsd honesty", () => {
    expect(formatCeilingUsd(1.5)).toBe("$1.5000");
    expect(formatCeilingUsd(Number.POSITIVE_INFINITY)).toMatch(/unknown/i);
  });
});
