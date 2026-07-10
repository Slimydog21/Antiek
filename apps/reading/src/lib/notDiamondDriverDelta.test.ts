import { describe, expect, it } from "vitest";
import {
  notDiamondBenchDelta,
  notDiamondBenchDeltaLabel,
  notDiamondDriverDelta,
  notDiamondDriverDeltaLabel,
} from "./notDiamondDriverDelta";

describe("notDiamondDriverDelta (rl)", () => {
  it("reports no_suggestion when advisory empty", () => {
    const d = notDiamondDriverDelta({
      suggestedModelId: null,
      installedModelId: "glm-5.2",
    });
    expect(d.status).toBe("no_suggestion");
    expect(d.advisory_only).toBe(true);
    expect(d.installed).toBe("glm-5.2");
    expect(notDiamondDriverDeltaLabel(d)).toMatch(/No advisory model/i);
  });

  it("reports no_installed when driver missing", () => {
    const d = notDiamondDriverDelta({
      suggestedModelId: "stub-strong",
      installedModelId: "",
    });
    expect(d.status).toBe("no_installed");
    expect(d.suggested).toBe("stub-strong");
    expect(notDiamondDriverDeltaLabel(d)).toMatch(/No driver installed/i);
    expect(notDiamondDriverDeltaLabel(d)).toMatch(/stub-strong/);
  });

  it("reports match when equal", () => {
    const d = notDiamondDriverDelta({
      suggestedModelId: "stub-strong",
      installedModelId: "stub-strong",
    });
    expect(d.status).toBe("match");
    expect(notDiamondDriverDeltaLabel(d)).toMatch(/matches advisory/i);
  });

  it("reports differs when installed ≠ suggested (never auto-applied)", () => {
    const d = notDiamondDriverDelta({
      suggestedModelId: "stub-strong",
      installedModelId: "glm-5.2",
    });
    expect(d.status).toBe("differs");
    expect(d.advisory_only).toBe(true);
    expect(notDiamondDriverDeltaLabel(d)).toMatch(/differs/i);
    expect(notDiamondDriverDeltaLabel(d)).toMatch(/not auto-applied/i);
  });
});

describe("notDiamondBenchDelta (ade)", () => {
  it("reports no_nd when advisory empty", () => {
    const d = notDiamondBenchDelta({
      ndSuggestedModelId: "",
      benchRecommendedModelId: "strong-model",
    });
    expect(d.status).toBe("no_nd");
    expect(d.advisory_only).toBe(true);
    expect(notDiamondBenchDeltaLabel(d)).toMatch(/No NotDiamond advisory/i);
  });

  it("reports no_bench when leaderboard unset", () => {
    const d = notDiamondBenchDelta({
      ndSuggestedModelId: "stub-strong",
      benchRecommendedModelId: null,
    });
    expect(d.status).toBe("no_bench");
    expect(notDiamondBenchDeltaLabel(d)).toMatch(/rank unset/i);
  });

  it("reports agree when ND and bench pick same model (case-insensitive)", () => {
    const d = notDiamondBenchDelta({
      ndSuggestedModelId: "Stub-Strong",
      benchRecommendedModelId: "stub-strong",
    });
    expect(d.status).toBe("agree");
    expect(notDiamondBenchDeltaLabel(d)).toMatch(/agree/i);
    expect(notDiamondBenchDeltaLabel(d)).toMatch(/advisory only/i);
  });

  it("reports diverge when ND and bench differ (neither auto-routes)", () => {
    const d = notDiamondBenchDelta({
      ndSuggestedModelId: "stub-strong",
      benchRecommendedModelId: "glm-5.2",
    });
    expect(d.status).toBe("diverge");
    expect(d.advisory_only).toBe(true);
    expect(notDiamondBenchDeltaLabel(d)).toMatch(/diverge/i);
    expect(notDiamondBenchDeltaLabel(d)).toMatch(/neither auto-routes/i);
  });
});
