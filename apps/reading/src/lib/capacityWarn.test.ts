import { afterEach, describe, expect, it } from "vitest";
import {
  formatCapacityWarnToast,
  parseCapacityWarning,
  stashCapacityWarning,
  takeCapacityWarning,
} from "./capacityWarn";

afterEach(() => {
  sessionStorage.clear();
});

describe("capacityWarn", () => {
  it("parses API soft-warn payload", () => {
    const w = parseCapacityWarning({
      code: "compute_capacity_soft_warn",
      message: "near capacity",
      used_compute_units: 90,
      monthly_compute_units: 100,
      enforcement: "soft",
      used_status: "known",
    });
    expect(w?.used_compute_units).toBe(90);
    expect(formatCapacityWarnToast(w!)).toContain("90/100 ACU");
  });

  it("stash/take is one-shot", () => {
    stashCapacityWarning("inv-1", {
      code: "compute_capacity_soft_warn",
      message: "near",
      used_compute_units: 85,
      monthly_compute_units: 100,
      enforcement: "soft",
      used_status: "known",
    });
    expect(takeCapacityWarning("inv-1")?.used_compute_units).toBe(85);
    expect(takeCapacityWarning("inv-1")).toBeNull();
  });
});
