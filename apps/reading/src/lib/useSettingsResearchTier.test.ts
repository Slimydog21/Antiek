import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
);

vi.mock("../api/settings", () => ({
  estimatePromptCost: vi.fn(async () => ({
    estimated_usd_low: null,
    estimated_usd_high: null,
    would_exceed_budget: null,
    pricing_known: false,
    notes: [],
    assumed_input_tokens: 500,
    assumed_output_tokens: 500,
    tier: null,
    provider: null,
    model: null,
  })),
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

import { useSettingsResearchTier } from "./useSettingsResearchTier";

describe("useSettingsResearchTier residual (jj)", () => {
  beforeEach(() => {
    fetchDepthTiers.mockReset().mockResolvedValue({
      active_depth_tier: null,
      active_preset: null,
      tiers: [],
    });
  });

  afterEach(() => cleanup());

  it("defaults to deep when Settings has no active depth tier", async () => {
    const { result } = renderHook(() => useSettingsResearchTier());
    expect(result.current.researchTier).toBe("deep");
    await waitFor(() => {
      expect(result.current.depthPrefill).toBe("none");
    });
    expect(result.current.researchTier).toBe("deep");
  });

  it("maps Settings wrestle → researchTier wrestle", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    const { result } = renderHook(() => useSettingsResearchTier());
    await waitFor(() => {
      expect(result.current.depthPrefill).toBe("installed");
    });
    expect(result.current.researchTier).toBe("wrestle");
    expect(fetchDepthTiers).toHaveBeenCalled();
  });

  it("maps flash → fast", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "flash",
      active_preset: null,
      tiers: [],
    });
    const { result } = renderHook(() => useSettingsResearchTier());
    await waitFor(() => {
      expect(result.current.depthPrefill).toBe("installed");
    });
    expect(result.current.researchTier).toBe("fast");
  });

  it("fetch failure is offline-honest (error + keep default deep)", async () => {
    fetchDepthTiers.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useSettingsResearchTier());
    await waitFor(() => {
      expect(result.current.depthPrefill).toBe("error");
    });
    expect(result.current.researchTier).toBe("deep");
  });
});
