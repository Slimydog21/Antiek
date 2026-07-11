import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  formatFractionUsed,
  formatMoney,
  formatOverBudget,
  formatWouldExceed,
  projectUsageBar,
} from "./usageBar";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("honesty formatters", () => {
  it("money null is unknown not $0", () => {
    expect(formatMoney(null)).toMatch(/unknown/i);
    expect(formatMoney(null)).not.toBe("$0.0000");
    expect(formatMoney(1.5)).toBe("$1.5000");
  });

  it("would_exceed null is unknown not within", () => {
    expect(formatWouldExceed(null)).toMatch(/unknown/i);
    expect(formatWouldExceed(null)).not.toMatch(/within/i);
    expect(formatWouldExceed(true)).toMatch(/exceed/i);
    expect(formatWouldExceed(false)).toMatch(/within/i);
  });

  it("fraction and over_budget null are unknown", () => {
    expect(formatFractionUsed(null)).toBe("unknown");
    expect(formatFractionUsed(0.25)).toBe("25.0%");
    expect(formatOverBudget(null)).toBe("unknown");
    expect(formatOverBudget(true)).toMatch(/over/i);
  });
});

describe("projectUsageBar", () => {
  it("POSTs usage-bar project and returns body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        usage_bar: {
          daily_cap_usd: 10,
          spent_usd: 2,
          remaining_usd: 8,
          over_budget: false,
          fraction_used: 0.2,
          spend_basis: "reserved_estimate",
          notes: [],
        },
        prompt_projection: {
          projected_cost_usd_low: 0.5,
          projected_cost_usd_high: 1,
          remaining_before_usd: 8,
          remaining_after_high_usd: 7,
          would_exceed: false,
          notes: [],
        },
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await projectUsageBar({
      daily_cap_usd: 10,
      spent_usd: 2,
      projected_cost_usd_high: 1,
    });
    expect(body.usage_bar.remaining_usd).toBe(8);
    expect(body.prompt_projection?.would_exceed).toBe(false);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/settings/usage-bar/project");
    expect(init?.method).toBe("POST");
    const payload = JSON.parse(init?.body as string);
    expect(payload.daily_cap_usd).toBe(10);
    expect(payload.spent_usd).toBe(2);
  });

  it("sends nulls when omitted (no zero invent)", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        usage_bar: {
          daily_cap_usd: null,
          spent_usd: null,
          remaining_usd: null,
          over_budget: null,
          fraction_used: null,
          spend_basis: "reserved_estimate",
          notes: [],
        },
      }),
      text: async () => "",
    } as unknown as Response);

    await projectUsageBar({});
    const payload = JSON.parse(mockFetch.mock.calls[0][1].body as string);
    expect(payload.daily_cap_usd).toBeNull();
    expect(payload.spent_usd).toBeNull();
  });
});
