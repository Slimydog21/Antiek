import { describe, expect, it } from "vitest";
import {
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
