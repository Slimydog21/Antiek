import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));

import { apiFetch } from "../lib/api";
import { fetchWeeklyBenchView, formatScore } from "./antiekBench";

const mockFetch = vi.mocked(apiFetch);

beforeEach(() => mockFetch.mockReset());

const measured = {
  authority: "advisory",
  status: "measured",
  week_id: "2026-W28",
  generated_at: "2026-07-08T00:00:00+00:00",
  measurements: [
    {
      task: "deep_research",
      tier: "pro",
      provider: "zai",
      model: "glm",
      score: 0.9,
      samples: 12,
    },
  ],
  notes: [],
};

describe("fetchWeeklyBenchView", () => {
  it("GETs server-owned evidence and validates it", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => measured,
    } as Response);
    const body = await fetchWeeklyBenchView();
    expect(body.measurements[0].score).toBe(0.9);
    expect(mockFetch).toHaveBeenCalledWith("/settings/antiek-bench/weekly");
  });

  it("rejects fabricated or inconsistent measurements", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...measured, status: "unavailable" }),
    } as Response);
    await expect(fetchWeeklyBenchView()).rejects.toThrow(/unavailable/);
  });

  it("formats measured scores without inventing missing values", () => {
    expect(formatScore(0.85)).toBe("0.850");
  });
});
