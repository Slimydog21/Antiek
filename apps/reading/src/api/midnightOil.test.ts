import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  approveMidnightOilCeiling,
  createMidnightOilJob,
  getMidnightOilJob,
} from "./midnightOil";

const mockFetch = vi.fn();

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => mockFetch(...args),
}));

describe("midnightOil API client", () => {
  beforeEach(() => mockFetch.mockReset());

  it("createMidnightOilJob posts goals + duration", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
      }),
    });
    const out = await createMidnightOilJob({
      goals: ["g"],
      duration_minutes: 60,
    });
    expect(out.recommended_price_ceiling_usd).toBe(3.6);
    expect(out.view_format).toBe("html");
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/create",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("approveMidnightOilCeiling posts use_recommended", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "approved",
        recommended_price_ceiling_usd: 3.6,
        approved_ceiling_usd: 3.6,
        view_format: "html",
        runnable: true,
      }),
    });
    const out = await approveMidnightOilCeiling({
      job_id: "moil_1",
      use_recommended: true,
    });
    expect(out.runnable).toBe(true);
    expect(out.status).toBe("approved");
  });

  it("getMidnightOilJob fetches by id", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "approved",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: true,
      }),
    });
    const out = await getMidnightOilJob("moil_1");
    expect(out.job_id).toBe("moil_1");
    expect(mockFetch.mock.calls[0][0]).toBe("/midnight-oil/jobs/moil_1");
  });
});
