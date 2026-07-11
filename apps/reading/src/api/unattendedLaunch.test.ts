import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  UnattendedBriefHttpError,
  formatUnattendedSummary,
  parseUnattendedBriefResult,
  postUnattendedBrief,
} from "./unattendedLaunch";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const sample = {
  duration_minutes: 90,
  goals: ["deep research"],
  approved_ceiling_cents: 250,
  recommended_ceiling_cents: 200,
  notes: ["live_execution_authorized=false"],
  live_execution_authorized: false,
  authority: "operator_brief_only",
};

describe("parseUnattendedBriefResult", () => {
  it("parses valid brief", () => {
    const r = parseUnattendedBriefResult(sample);
    expect(r.live_execution_authorized).toBe(false);
    expect(r.goals).toEqual(["deep research"]);
  });

  it("rejects live_execution_authorized=true", () => {
    expect(() =>
      parseUnattendedBriefResult({ ...sample, live_execution_authorized: true }),
    ).toThrow(/live_execution_authorized/);
  });

  it("rejects missing goals", () => {
    expect(() =>
      parseUnattendedBriefResult({ ...sample, goals: [] }),
    ).toThrow(/goals/);
  });
});

describe("postUnattendedBrief", () => {
  it("POSTs and validates", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const r = await postUnattendedBrief({
      duration_minutes: 90,
      goals: ["deep research"],
      approved_ceiling_cents: 250,
      recommended_ceiling_cents: 200,
    });
    expect(r.authority).toBe("operator_brief_only");
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/unattended/brief",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects empty goals without network", async () => {
    await expect(
      postUnattendedBrief({
        duration_minutes: 60,
        goals: [],
        approved_ceiling_cents: 1,
      }),
    ).rejects.toThrow(/goals/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postUnattendedBrief({
        duration_minutes: 60,
        goals: ["x"],
        approved_ceiling_cents: 1,
      }),
    ).rejects.toBeInstanceOf(UnattendedBriefHttpError);
  });
});

describe("formatUnattendedSummary", () => {
  it("summarizes", () => {
    expect(formatUnattendedSummary(parseUnattendedBriefResult(sample))).toMatch(
      /90 min/,
    );
  });
});
