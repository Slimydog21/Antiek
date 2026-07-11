import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  formatAuthority,
  formatWeight,
  parseUsageLearnProposal,
  postUsageLearn,
  UsageLearnHttpError,
} from "./benchUsageLearn";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("formatters", () => {
  it("authority and weight honesty", () => {
    expect(formatAuthority("advisory")).toMatch(/advisory/i);
    expect(formatAuthority(null)).toMatch(/unknown/i);
    expect(formatWeight(0.5)).toBe("0.5000");
    expect(formatWeight(null)).toBe("unknown");
  });
});

describe("parseUsageLearnProposal", () => {
  it("requires authority=advisory", () => {
    expect(() =>
      parseUsageLearnProposal({
        authority: "production",
        task_weights: [],
      }),
    ).toThrow(/advisory/);
    const ok = parseUsageLearnProposal({
      week_id: "2026-W28",
      authority: "advisory",
      incomplete: false,
      notes: ["ok"],
      suggested_new_tasks: [],
      task_weights: [
        {
          task: "deep_research",
          weight: 0.7,
          prior_weight: null,
          n_success: 1,
          n_failure: 1,
          rationale: "failure-driven",
        },
      ],
    });
    expect(ok.authority).toBe("advisory");
    expect(ok.task_weights[0].task).toBe("deep_research");
  });
});

describe("postUsageLearn", () => {
  it("POSTs usage-learn and validates body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        week_id: "2026-W28",
        authority: "advisory",
        incomplete: false,
        notes: [],
        suggested_new_tasks: [],
        task_weights: [
          {
            task: "general",
            weight: 1,
            prior_weight: null,
            n_success: 1,
            n_failure: 0,
            rationale: "stable",
          },
        ],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postUsageLearn({
      week_id: "2026-W28",
      usage_events: [{ task: "general", success: true }],
    });
    expect(body.authority).toBe("advisory");
    expect(mockFetch).toHaveBeenCalledWith(
      "/settings/antiek-bench/usage-learn",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects non-advisory 200", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        authority: "authoritative",
        task_weights: [],
      }),
      text: async () => "",
    } as unknown as Response);
    await expect(postUsageLearn({})).rejects.toThrow(/advisory/);
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 422,
      text: async () => "bad success type",
      json: async () => ({}),
    } as unknown as Response);
    await expect(postUsageLearn({})).rejects.toBeInstanceOf(UsageLearnHttpError);
  });
});
