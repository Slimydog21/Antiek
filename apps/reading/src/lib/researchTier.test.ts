import { describe, expect, it } from "vitest";

import {
  formatResearchTierCeilingFactor,
  formatResearchTierDurationBand,
  mapDepthTierToResearchTier,
  mapResearchTierToBenchTaskClass,
  mapResearchTierToCeilingMultiplier,
  mapResearchTierToDepthTier,
  mapResearchTierToProgressPollMs,
  mapResearchTierToRecommendedDurationMinutes,
  RESEARCH_TIER_CEILING_MULTIPLIER,
  RESEARCH_TIER_PROGRESS_POLL_MS,
  RESEARCH_TIER_RECOMMENDED_DURATION_MINUTES,
} from "./researchTier";

describe("researchTier map residual (gt)", () => {
  it("maps Settings depth-tier flash|pro|wrestle to ResearchTier", () => {
    expect(mapDepthTierToResearchTier("flash")).toBe("fast");
    expect(mapDepthTierToResearchTier("pro")).toBe("deep");
    expect(mapDepthTierToResearchTier("wrestle")).toBe("wrestle");
  });

  it("accepts ResearchTier aliases as depth input", () => {
    expect(mapDepthTierToResearchTier("fast")).toBe("fast");
    expect(mapDepthTierToResearchTier("deep")).toBe("deep");
  });

  it("returns null for unset/unknown so callers keep defaults", () => {
    expect(mapDepthTierToResearchTier(null)).toBeNull();
    expect(mapDepthTierToResearchTier("")).toBeNull();
    expect(mapDepthTierToResearchTier("turbo")).toBeNull();
  });

  it("maps ResearchTier back to Settings depth-tier ids", () => {
    expect(mapResearchTierToDepthTier("fast")).toBe("flash");
    expect(mapResearchTierToDepthTier("deep")).toBe("pro");
    expect(mapResearchTierToDepthTier("wrestle")).toBe("wrestle");
    expect(mapResearchTierToDepthTier(null)).toBeNull();
  });
});

describe("researchTier map residual (gw) bench task_class", () => {
  it("maps ResearchTier to Antiek-bench task_class", () => {
    expect(mapResearchTierToBenchTaskClass("wrestle")).toBe("wrestle");
    expect(mapResearchTierToBenchTaskClass("fast")).toBe("distill");
    expect(mapResearchTierToBenchTaskClass("flash")).toBe("distill");
    expect(mapResearchTierToBenchTaskClass("deep")).toBe("synthesize");
    expect(mapResearchTierToBenchTaskClass("pro")).toBe("synthesize");
    expect(mapResearchTierToBenchTaskClass(null)).toBeNull();
    expect(mapResearchTierToBenchTaskClass("unknown")).toBeNull();
  });
});

describe("researchTier map residual (ju) progress poll cadence", () => {
  it("maps closed tiers to poll ms (fast 2s · deep 4s · wrestle 8s)", () => {
    expect(mapResearchTierToProgressPollMs("fast")).toBe(
      RESEARCH_TIER_PROGRESS_POLL_MS.fast,
    );
    expect(mapResearchTierToProgressPollMs("deep")).toBe(
      RESEARCH_TIER_PROGRESS_POLL_MS.deep,
    );
    expect(mapResearchTierToProgressPollMs("wrestle")).toBe(
      RESEARCH_TIER_PROGRESS_POLL_MS.wrestle,
    );
    expect(mapResearchTierToProgressPollMs("flash")).toBe(2000);
    expect(mapResearchTierToProgressPollMs(null)).toBe(4000);
    expect(mapResearchTierToProgressPollMs("turbo")).toBe(4000);
  });
});

describe("researchTier map residual (jv) MO ceiling multiplier", () => {
  it("mirrors substrate midnight_oil.ceiling TIER_MULTIPLIER", () => {
    expect(mapResearchTierToCeilingMultiplier("fast")).toBe(
      RESEARCH_TIER_CEILING_MULTIPLIER.fast,
    );
    expect(mapResearchTierToCeilingMultiplier("deep")).toBe(1.0);
    expect(mapResearchTierToCeilingMultiplier("wrestle")).toBe(2.0);
    expect(mapResearchTierToCeilingMultiplier(null)).toBe(1.0);
    expect(formatResearchTierCeilingFactor("wrestle")).toBe("2.0× (wrestle)");
    expect(formatResearchTierCeilingFactor("fast")).toBe("0.5× (fast)");
    expect(formatResearchTierCeilingFactor("deep")).toBe("1.0× (deep)");
  });
});

describe("researchTier residual (ada) MO ceiling formula constants", () => {
  it("mirrors substrate midnight_oil.ceiling TOKENS/SAFETY/FANOUT", async () => {
    const {
      MOIL_CEILING_DEFAULT_FANOUT_DEPTH,
      MOIL_CEILING_SAFETY_FACTOR,
      MOIL_CEILING_TOKENS_PER_MINUTE,
    } = await import("./researchTier");
    expect(MOIL_CEILING_TOKENS_PER_MINUTE).toBe(4000);
    expect(MOIL_CEILING_SAFETY_FACTOR).toBe(1.25);
    expect(MOIL_CEILING_DEFAULT_FANOUT_DEPTH).toBe(3);
  });
});

describe("researchTier map residual (ng) MO recommended duration", () => {
  it("maps closed tiers to competitive duration midpoints (parity mw)", () => {
    expect(mapResearchTierToRecommendedDurationMinutes("fast")).toBe(
      RESEARCH_TIER_RECOMMENDED_DURATION_MINUTES.fast,
    );
    expect(mapResearchTierToRecommendedDurationMinutes("deep")).toBe(10);
    expect(mapResearchTierToRecommendedDurationMinutes("wrestle")).toBe(30);
    expect(mapResearchTierToRecommendedDurationMinutes("flash")).toBe(3);
    expect(mapResearchTierToRecommendedDurationMinutes(null)).toBe(10);
    expect(formatResearchTierDurationBand("fast")).toBe("1–3");
    expect(formatResearchTierDurationBand("deep")).toBe("3–10");
    expect(formatResearchTierDurationBand("wrestle")).toBe("10–30+");
  });
});
