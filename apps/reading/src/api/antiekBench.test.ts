import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  fetchWeeklyBenchView,
  formatBestModel,
  formatScore,
} from "./antiekBench";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("formatters", () => {
  it("null score is NOT MEASURED not 0", () => {
    expect(formatScore(null)).toBe("NOT MEASURED");
    expect(formatScore(undefined)).toBe("NOT MEASURED");
    expect(formatScore(0.85)).toBe("0.850");
  });

  it("missing best model is none", () => {
    expect(formatBestModel(undefined)).toBe("none");
    expect(formatBestModel("thinker")).toBe("thinker");
  });
});

describe("fetchWeeklyBenchView", () => {
  it("POSTs weekly view and returns body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        week_id: "2026-W28",
        authority: "advisory",
        best_by_task: { deep_research: "thinker" },
        incomplete: false,
        notes: [],
        scores: [
          {
            task: "deep_research",
            model_id: "thinker",
            score: 0.9,
            n_runs: 2,
            notes: "",
          },
        ],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await fetchWeeklyBenchView({
      week_id: "2026-W28",
      records: [{ task: "deep_research", model_id: "thinker", score: 0.9 }],
    });
    expect(body.authority).toBe("advisory");
    expect(body.best_by_task.deep_research).toBe("thinker");
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/settings/antiek-bench/weekly");
    expect(init?.method).toBe("POST");
  });
});
