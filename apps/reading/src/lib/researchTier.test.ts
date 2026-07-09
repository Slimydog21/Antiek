import { describe, expect, it } from "vitest";

import {
  mapDepthTierToResearchTier,
  mapResearchTierToDepthTier,
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
