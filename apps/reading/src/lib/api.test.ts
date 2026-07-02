import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  FAILURE_HEADLINES,
  classifyClientError,
  startInvestigation,
} from "./api";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function postedJsonBody(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(typeof init.body).toBe("string");
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("classifyClientError", () => {
  it("parses each backend failure code from detail envelope", () => {
    for (const code of [
      "provider_unconfigured",
      "provider_upstream_error",
      "timeout",
      "unknown",
    ] as const) {
      const body = JSON.stringify({
        detail: { code, message: "safe", retryable: code !== "provider_unconfigured" },
      });
      const c = classifyClientError(new ApiError("fail", 503, body));
      expect(c.code).toBe(code);
    }
  });

  it("downgrades unparseable ApiError body to unknown", () => {
    const c = classifyClientError(new ApiError("fail", 500, "not json"));
    expect(c.code).toBe("unknown");
  });

  it("downgrades unrecognized server code to unknown", () => {
    const body = JSON.stringify({ detail: { code: "rate_limit_exceeded" } });
    const c = classifyClientError(new ApiError("fail", 429, body));
    expect(c.code).toBe("unknown");
  });

  it("maps non-ApiError throws to backend_unreachable", () => {
    const c = classifyClientError(new TypeError("Failed to fetch"));
    expect(c.code).toBe("backend_unreachable");
  });

  it("renders headline for real backend wire shape (SPR-04 seam)", () => {
    const body = JSON.stringify({
      detail: {
        code: "provider_unconfigured",
        message:
          "No model provider is configured. Set a provider key and restart.",
        retryable: false,
      },
    });
    const c = classifyClientError(new ApiError("fail", 503, body));
    expect(c.code).toBe("provider_unconfigured");
    expect(FAILURE_HEADLINES[c.code]).toMatch(/No model provider is configured/);
  });
});

describe("lib/api startInvestigation boundary", () => {
  it("trims launch request text and optional handles before sending", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        investigation_id: " inv-started ",
        status: "in_progress",
        start_event_id: " ev-start ",
      }),
    );

    await expect(
      startInvestigation({
        question: "  What changed?  ",
        context: "  source passage  ",
        topic_slug: "  climate-risk  ",
        parent_investigation_id: " inv-parent ",
        spawn_context: " selected passage ",
        max_sub_questions: 3,
        investigation_id: " inv-reserved ",
        research_tier: "fast",
      }),
    ).resolves.toEqual({
      investigation_id: "inv-started",
      status: "in_progress",
      start_event_id: "ev-start",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/investigations");
    expect(postedJsonBody()).toEqual({
      question: "What changed?",
      context: "source passage",
      topic_slug: "climate-risk",
      parent_investigation_id: "inv-parent",
      spawn_context: "selected passage",
      max_sub_questions: 3,
      investigation_id: "inv-reserved",
      research_tier: "fast",
    });
  });

  it("drops blank optional launch fields and unsupported research tiers", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        investigation_id: "inv-started",
        status: "in_progress",
        start_event_id: "ev-start",
      }),
    );

    await startInvestigation({
      question: "Question",
      context: " ",
      topic_slug: " ",
      parent_investigation_id: " ",
      spawn_context: " ",
      investigation_id: " ",
      research_tier: "turbo" as "deep",
    });

    expect(postedJsonBody()).toEqual({ question: "Question" });
  });

  it("rejects malformed launch requests before sending", async () => {
    await expect(startInvestigation({ question: " " })).rejects.toThrow(/question/);
    await expect(
      startInvestigation({ question: "Question", max_sub_questions: 0 }),
    ).rejects.toThrow(/max_sub_questions/);
    await expect(
      startInvestigation({ question: "Question", max_sub_questions: Number.POSITIVE_INFINITY }),
    ).rejects.toThrow(/max_sub_questions/);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
