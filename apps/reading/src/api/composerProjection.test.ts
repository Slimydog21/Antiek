import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import { fetchComposerProjection } from "./composerProjection";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

const projection = {
  task: "deep_research",
  recommended_tier: "pro",
  ranked_candidates: [],
  budget: { daily_cap_usd: 10, spent_usd: 3 },
  remaining_usd: 7,
  chosen_provider: "openai",
  chosen_model: "gpt-pro",
  chosen_projection: {
    seam_id: "composer",
    provider: "openai",
    model: "gpt-pro",
    operation: "deep_research",
    maximum_cost_usd: "1E-1000",
    reservation_cents: 1,
    disposition: "hold_eligible",
    ineligibility: null,
  },
  would_exceed_budget: false,
  pricing_status: "known",
  authority: "advisory_explanatory",
  notes: [],
  fallback_plan: null,
};

const fallbackPlan = {
  authority: "advisory_fallback_plan",
  tier: "pro",
  status: "executable",
  maximum_chain_exposure_cents: 20,
  would_exceed_budget: false,
  routes: [
    {
      fallback_index: 0,
      provider: "openai",
      model: "gpt-pro",
      registered: true,
      projection: {
        maximum_cost_usd: "0.2",
        reservation_cents: 20,
        disposition: "hold_eligible",
        ineligibility: null,
        rate_snapshot: "rates-v1",
      },
      hard_ceiling_eligible: true,
      execution_status: "executable",
    },
    {
      fallback_index: 1,
      provider: "fallback",
      model: "model-b",
      registered: true,
      projection: {
        maximum_cost_usd: "0.1",
        reservation_cents: 10,
        disposition: "hold_eligible",
        ineligibility: null,
        rate_snapshot: "rates-v1",
      },
      hard_ceiling_eligible: true,
      execution_status: "executable",
    },
  ],
};

beforeEach(() => {
  mockFetch.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchComposerProjection", () => {
  it("sends only caller-owned prompt bounds and route identity", async () => {
    mockFetch.mockResolvedValue(response(projection));

    await fetchComposerProjection({
      task: "deep_research",
      bounded_usage: [
        { unit: "input_token", maximum: 10_000 },
        { unit: "output_token", maximum: 2_000 },
      ],
      choice: { provider: "openai", model: "gpt-pro" },
      seam_id: "composer",
      operation: "deep_research",
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/settings/composer-projection/resolve");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toEqual({
      task: "deep_research",
      bounded_usage: [
        { unit: "input_token", maximum: 10_000 },
        { unit: "output_token", maximum: 2_000 },
      ],
      choice: { provider: "openai", model: "gpt-pro" },
      seam_id: "composer",
      operation: "deep_research",
    });
    expect(body).not.toHaveProperty("candidates");
  });

  it("preserves the server Decimal string without IEEE-754 coercion", async () => {
    mockFetch.mockResolvedValue(response(projection));

    const result = await fetchComposerProjection({
      task: "deep_research",
      bounded_usage: [{ unit: "call", maximum: 1 }],
    });

    expect(result.chosen_projection?.maximum_cost_usd).toBe("1E-1000");
    expect(typeof result.chosen_projection?.maximum_cost_usd).toBe("string");
  });

  it("rejects a numeric maximum cost instead of silently accepting precision loss", async () => {
    mockFetch.mockResolvedValue(
      response({
        ...projection,
        chosen_projection: {
          ...projection.chosen_projection,
          maximum_cost_usd: 1e-300,
        },
      }),
    );

    await expect(
      fetchComposerProjection({
        task: "deep_research",
        bounded_usage: [{ unit: "call", maximum: 1 }],
      }),
    ).rejects.toThrow("invalid exact cost");
  });

  it("rejects an unsafe integer reservation", async () => {
    mockFetch.mockResolvedValue(
      response({
        ...projection,
        chosen_projection: {
          ...projection.chosen_projection,
          reservation_cents: Number.MAX_SAFE_INTEGER + 1,
        },
      }),
    );

    await expect(
      fetchComposerProjection({
        task: "deep_research",
        bounded_usage: [{ unit: "call", maximum: 1 }],
      }),
    ).rejects.toThrow("invalid exact cost");
  });

  it("preserves a structurally valid max-not-sum fallback plan", async () => {
    mockFetch.mockResolvedValue(
      response({ ...projection, fallback_plan: fallbackPlan }),
    );
    const result = await fetchComposerProjection({
      task: "deep_research",
      bounded_usage: [{ unit: "call", maximum: 1 }],
    });
    expect(result.fallback_plan?.maximum_chain_exposure_cents).toBe(20);
    expect(result.fallback_plan?.routes).toHaveLength(2);
  });

  it("rejects duplicate or non-contiguous fallback routes", async () => {
    mockFetch.mockResolvedValue(
      response({
        ...projection,
        fallback_plan: {
          ...fallbackPlan,
          routes: [
            fallbackPlan.routes[0],
            { ...fallbackPlan.routes[0], fallback_index: 2 },
          ],
        },
      }),
    );
    await expect(
      fetchComposerProjection({
        task: "deep_research",
        bounded_usage: [{ unit: "call", maximum: 1 }],
      }),
    ).rejects.toThrow(/invalid fallback route|duplicate fallback routes/);
  });

  it("rejects a summed or unsafe chain exposure", async () => {
    for (const exposure of [30, Number.MAX_SAFE_INTEGER + 1]) {
      mockFetch.mockResolvedValueOnce(
        response({
          ...projection,
          fallback_plan: {
            ...fallbackPlan,
            maximum_chain_exposure_cents: exposure,
          },
        }),
      );
      await expect(
        fetchComposerProjection({
          task: "deep_research",
          bounded_usage: [{ unit: "call", maximum: 1 }],
        }),
      ).rejects.toThrow("contradictory fallback authority");
    }
  });

  it("rejects blocked authority that claims exposure or a budget verdict", async () => {
    mockFetch.mockResolvedValue(
      response({
        ...projection,
        fallback_plan: {
          ...fallbackPlan,
          status: "blocked",
          routes: [
            {
              ...fallbackPlan.routes[0],
              hard_ceiling_eligible: false,
              execution_status: "blocked_selection_authority",
            },
          ],
        },
      }),
    );
    await expect(
      fetchComposerProjection({
        task: "deep_research",
        bounded_usage: [{ unit: "call", maximum: 1 }],
      }),
    ).rejects.toThrow("contradictory fallback authority");
  });
});
