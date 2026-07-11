import { describe, expect, it } from "vitest";
import {
  computeUsageBar,
  formatProjectionSummary,
  projectPromptAgainstBar,
} from "./promptProjection";

describe("computeUsageBar", () => {
  it("computes remaining and fraction", () => {
    const bar = computeUsageBar({
      daily_cap_usd: 10,
      spent_usd: 3,
    });
    expect(bar.remaining_usd).toBe(7);
    expect(bar.over_budget).toBe(false);
    expect(bar.fraction_used).toBeCloseTo(0.3);
  });

  it("keeps remaining null when cap unknown (no invent 0)", () => {
    const bar = computeUsageBar({
      daily_cap_usd: null,
      spent_usd: 1,
    });
    expect(bar.remaining_usd).toBeNull();
    expect(bar.fraction_used).toBeNull();
    expect(bar.over_budget).toBeNull();
  });

  it("rejects non-finite", () => {
    expect(() =>
      computeUsageBar({ daily_cap_usd: Number.NaN, spent_usd: 1 }),
    ).toThrow(/finite/);
  });

  it("rejects overflow remaining", () => {
    expect(() =>
      computeUsageBar({
        daily_cap_usd: Number.MAX_VALUE,
        spent_usd: -Number.MAX_VALUE,
      }),
    ).toThrow(/non-finite|overflow/);
  });

  it("rejects overflow fraction_used", () => {
    // remaining stays finite (MIN_VALUE - MAX_VALUE), but spent/cap → Infinity
    expect(() =>
      computeUsageBar({
        daily_cap_usd: Number.MIN_VALUE,
        spent_usd: Number.MAX_VALUE,
      }),
    ).toThrow(/non-finite|overflow|fraction/);
  });
});

describe("projectPromptAgainstBar", () => {
  it("would_exceed true when high > remaining", () => {
    const bar = computeUsageBar({ daily_cap_usd: 10, spent_usd: 8 });
    const p = projectPromptAgainstBar(bar, {
      projected_cost_usd_low: 1,
      projected_cost_usd_high: 3,
    });
    expect(p.would_exceed).toBe(true);
    expect(p.remaining_after_high_usd).toBe(-1);
  });

  it("would_exceed false when high <= remaining", () => {
    const bar = computeUsageBar({ daily_cap_usd: 10, spent_usd: 1 });
    const p = projectPromptAgainstBar(bar, {
      projected_cost_usd_low: 0.5,
      projected_cost_usd_high: 2,
    });
    expect(p.would_exceed).toBe(false);
  });

  it("would_exceed null when remaining unknown", () => {
    const bar = computeUsageBar({ daily_cap_usd: null, spent_usd: null });
    const p = projectPromptAgainstBar(bar, {
      projected_cost_usd_low: 1,
      projected_cost_usd_high: 2,
    });
    expect(p.would_exceed).toBeNull();
    expect(p.remaining_after_high_usd).toBeNull();
  });

  it("would_exceed null when high unknown", () => {
    const bar = computeUsageBar({ daily_cap_usd: 10, spent_usd: 1 });
    const p = projectPromptAgainstBar(bar, {
      projected_cost_usd_low: 1,
      projected_cost_usd_high: null,
    });
    expect(p.would_exceed).toBeNull();
  });

  it("rejects after-high overflow", () => {
    const bar = computeUsageBar({
      daily_cap_usd: Number.MAX_VALUE,
      spent_usd: 0,
    });
    expect(() =>
      projectPromptAgainstBar(bar, {
        projected_cost_usd_low: 0,
        projected_cost_usd_high: -Number.MAX_VALUE,
      }),
    ).toThrow(/non-finite|overflow/);
  });
});

describe("formatProjectionSummary", () => {
  it("summarizes", () => {
    const bar = computeUsageBar({ daily_cap_usd: 5, spent_usd: 1 });
    const p = projectPromptAgainstBar(bar, {
      projected_cost_usd_low: 1,
      projected_cost_usd_high: 1,
    });
    expect(formatProjectionSummary(p)).toMatch(/would_exceed=false/);
  });
});
