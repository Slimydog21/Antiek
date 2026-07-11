import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  parsePriceCeilingHttpResult,
  postPriceCeilingRecommend,
  PriceCeilingHttpError,
} from "./priceCeilingHttp";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const okBody = {
  hours: 2,
  goal_count: 2,
  recommended_ceiling_usd: 5.5,
  low_usd: 3,
  high_usd: 7,
  authority: "advisory",
  notes: ["authority=advisory"],
};

describe("parsePriceCeilingHttpResult", () => {
  it("requires authority advisory and finite money", () => {
    expect(parsePriceCeilingHttpResult(okBody).authority).toBe("advisory");
    expect(() =>
      parsePriceCeilingHttpResult({ ...okBody, authority: "production" }),
    ).toThrow(/advisory/);
    expect(() =>
      parsePriceCeilingHttpResult({
        ...okBody,
        recommended_ceiling_usd: Number.POSITIVE_INFINITY,
      }),
    ).toThrow(/finite/);
  });
});

describe("postPriceCeilingRecommend", () => {
  it("POSTs recommend and returns validated body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => okBody,
      text: async () => "",
    } as unknown as Response);
    const body = await postPriceCeilingRecommend({
      hours: 2,
      goals: ["a", "b"],
    });
    expect(body.recommended_ceiling_usd).toBe(5.5);
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/price-ceiling/recommend",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects non-advisory 200", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...okBody, authority: "production" }),
      text: async () => "",
    } as unknown as Response);
    await expect(
      postPriceCeilingRecommend({ hours: 1 }),
    ).rejects.toThrow(/advisory/);
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "hours must be > 0",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postPriceCeilingRecommend({ hours: 0 }),
    ).rejects.toBeInstanceOf(PriceCeilingHttpError);
  });
});
