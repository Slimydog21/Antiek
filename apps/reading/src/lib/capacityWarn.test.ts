import { afterEach, describe, expect, it } from "vitest";
import {
  CapacityExhaustedError,
  formatCapacityExhaustedToast,
  formatCapacityWarnToast,
  parseCapacityExhaustedDetail,
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

  it("parses structured 429 exhausted detail", () => {
    const body = JSON.stringify({
      detail: {
        code: "compute_capacity_exhausted",
        message: "at capacity (5/5 ACU)",
        used_compute_units: 5,
        monthly_compute_units: 5,
        enforcement: "hard",
        used_status: "known",
        retryable: false,
      },
    });
    const ex = parseCapacityExhaustedDetail(429, body);
    expect(ex?.code).toBe("compute_capacity_exhausted");
    expect(ex?.used_compute_units).toBe(5);
    expect(formatCapacityExhaustedToast(ex!)).toContain("5/5 ACU");
    expect(formatCapacityExhaustedToast(ex!)).toContain("Settings");
  });

  it("parses legacy bare-string 429 detail", () => {
    const body = JSON.stringify({ detail: "compute_capacity_exhausted" });
    const ex = parseCapacityExhaustedDetail(429, body);
    expect(ex?.code).toBe("compute_capacity_exhausted");
    expect(ex?.message).toMatch(/Settings/);
  });

  it("ignores non-capacity 429s", () => {
    expect(
      parseCapacityExhaustedDetail(
        429,
        JSON.stringify({ detail: "rate_limited" }),
      ),
    ).toBeNull();
    expect(parseCapacityExhaustedDetail(503, "{}")).toBeNull();
  });

  it("CapacityExhaustedError carries exhaustion", () => {
    const ex = new CapacityExhaustedError({
      code: "compute_capacity_exhausted",
      message: "refused",
      used_compute_units: 10,
      monthly_compute_units: 10,
      enforcement: "hard",
      used_status: "known",
    });
    expect(ex).toBeInstanceOf(Error);
    expect(ex.name).toBe("CapacityExhaustedError");
    expect(ex.exhaustion.used_compute_units).toBe(10);
    expect(ex.message).toContain("10/10 ACU");
  });
});
