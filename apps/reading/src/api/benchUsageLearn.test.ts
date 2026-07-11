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
  const valid = {
    week_id: "2026-W28",
    authority: "advisory",
    incomplete: false,
    notes: ["ok"],
    suggested_new_tasks: [] as string[],
    task_weights: [
      {
        task: "deep_research",
        weight: 0.7,
        prior_weight: null as number | null,
        n_success: 1,
        n_failure: 1,
        rationale: "failure-driven",
      },
    ],
  };

  it("requires authority=advisory", () => {
    expect(() =>
      parseUsageLearnProposal({
        ...valid,
        authority: "production",
      }),
    ).toThrow(/advisory/);
    const ok = parseUsageLearnProposal(valid);
    expect(ok.authority).toBe("advisory");
    expect(ok.task_weights[0].task).toBe("deep_research");
  });

  it("rejects malformed weight rows without inventing defaults", () => {
    expect(() =>
      parseUsageLearnProposal({
        ...valid,
        task_weights: [{}],
      }),
    ).toThrow(/task/);
    expect(() =>
      parseUsageLearnProposal({
        ...valid,
        task_weights: [{ task: "x", weight: "0.5", n_success: 0, n_failure: 0, rationale: "" }],
      }),
    ).toThrow(/weight/);
    expect(() =>
      parseUsageLearnProposal({
        authority: "advisory",
        // missing incomplete / notes / week_id / arrays
        task_weights: [],
      }),
    ).toThrow();
    // missing prior_weight key must not invent null
    const { prior_weight: _pw, ...noPrior } = valid.task_weights[0];
    void _pw;
    expect(() =>
      parseUsageLearnProposal({
        ...valid,
        task_weights: [noPrior],
      }),
    ).toThrow(/prior_weight/);
    expect(() =>
      parseUsageLearnProposal({
        ...valid,
        notes: [1 as unknown as string],
      }),
    ).toThrow(/notes/);
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
