import { describe, expect, it } from "vitest";

import {
  ApiError,
  FAILURE_HEADLINES,
  classifyClientError,
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