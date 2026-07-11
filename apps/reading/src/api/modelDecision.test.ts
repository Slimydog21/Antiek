/**
 * Offline unit tests for the advisory model-decision client helpers + rank call shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  authorityIsAdvisory,
  formatRemaining,
  formatUsd,
  formatWouldExceed,
  rankModelsForTask,
} from "./modelDecision";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("honesty formatters", () => {
  it("would_exceed null is unknown, not false/$0", () => {
    expect(formatWouldExceed(null)).toMatch(/unknown/i);
    expect(formatWouldExceed(null)).not.toMatch(/within/i);
    expect(formatWouldExceed(true)).toMatch(/exceed/i);
    expect(formatWouldExceed(false)).toMatch(/within/i);
  });

  it("remaining null is unknown, not $0.0000", () => {
    expect(formatRemaining(null)).toMatch(/unknown/i);
    expect(formatRemaining(null)).not.toBe("$0.0000");
    expect(formatRemaining(1.25)).toBe("$1.2500");
  });

  it("formatUsd uses em-dash for null", () => {
    expect(formatUsd(null)).toBe("—");
    expect(formatUsd(0.0123)).toBe("$0.0123");
  });

  it("authority advisory check is strict", () => {
    expect(authorityIsAdvisory("advisory")).toBe(true);
    expect(authorityIsAdvisory("ADVISORY")).toBe(true);
    expect(authorityIsAdvisory("dispatch")).toBe(false);
    expect(authorityIsAdvisory(null)).toBe(false);
  });
});

describe("rankModelsForTask", () => {
  it("POSTs the advisory rank route and returns the body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        task: "deep_research",
        authority: "advisory",
        recommended_model_id: "thinker",
        remaining_usd: 0.5,
        prompt_chars: 1000,
        notes: ["authority=advisory"],
        ranked: [
          {
            model_id: "thinker",
            provider: "anthropic",
            tier: "reasoning",
            score: 1,
            rationale: "static",
            projected_cost_usd_low: 0.01,
            projected_cost_usd_high: 0.02,
            would_exceed: false,
          },
        ],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await rankModelsForTask({
      task: "deep_research",
      models: [{ model_id: "thinker", tier: "reasoning" }],
      remaining_usd: 0.5,
      prompt_chars: 1000,
    });

    expect(body.authority).toBe("advisory");
    expect(body.recommended_model_id).toBe("thinker");
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/settings/model-decision/rank");
    expect(init?.method).toBe("POST");
    const payload = JSON.parse(init?.body as string);
    expect(payload.task).toBe("deep_research");
    expect(payload.remaining_usd).toBe(0.5);
  });

  it("sends remaining_usd null when omitted (no zero invent)", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        task: "general",
        authority: "advisory",
        recommended_model_id: null,
        remaining_usd: null,
        prompt_chars: null,
        notes: [],
        ranked: [],
      }),
      text: async () => "",
    } as unknown as Response);

    await rankModelsForTask({
      task: "general",
      models: [],
    });
    const payload = JSON.parse(mockFetch.mock.calls[0][1].body as string);
    expect(payload.remaining_usd).toBeNull();
  });
});
