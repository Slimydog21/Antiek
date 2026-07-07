import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  FAILURE_HEADLINES,
  classifyClientError,
  listStaleRefreshResolutions,
} from "./api";

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

describe("listStaleRefreshResolutions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the graph-wide stale resolution list with bounded filters", async () => {
    const response = {
      count: 1,
      resolutions: [
        {
          event_id: "evt-resolution",
          investigation_id: "inv-refresh",
          emitted_at: "2026-07-07T15:05:00Z",
          parent_event_id: "evt-candidate",
          flag_id: "stale-edge-one-personnel",
          entity_kind: "edge",
          entity_id: "edge-one",
          status: "refreshed",
          notes: "resolved by stale refresh promotion",
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => response,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await listStaleRefreshResolutions({
      limit: 25,
      entityId: "edge-one",
    });

    expect(result).toEqual(response);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/stale-refresh/resolutions");
    expect(String(url)).toContain("limit=25");
    expect(String(url)).toContain("entity_id=edge-one");
    expect(init).toMatchObject({ credentials: "include" });
  });

  it("throws ApiError when the stale resolution list fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () => "down",
      }),
    );

    await expect(listStaleRefreshResolutions()).rejects.toMatchObject({
      status: 503,
      body: "down",
    });
  });
});
