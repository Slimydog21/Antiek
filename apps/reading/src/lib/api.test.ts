import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "../components/lemon/LemonToast";
import { CapacityExhaustedError, takeCapacityWarning } from "./capacityWarn";

import {
  ApiError,
  FAILURE_HEADLINES,
  classifyClientError,
  publishStartCapacityEffect,
  startInvestigation,
} from "./api";

const fetchMock = vi.fn();

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

describe("startInvestigation capacity effects", () => {
  const request = { question: "What changed?" };
  const warning = {
    code: "compute_capacity_soft_warn",
    message: "near capacity",
    used_compute_units: 9,
    monthly_compute_units: 10,
    enforcement: "soft",
    used_status: "known",
  };
  const exhaustion = {
    ...warning,
    code: "compute_capacity_exhausted",
    message: "at capacity",
    used_compute_units: 10,
    enforcement: "hard",
  };

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(toast, "err").mockImplementation(() => 0);
    vi.spyOn(toast, "warn").mockImplementation(() => 0);
  });

  afterEach(() => {
    sessionStorage.removeItem("antiek:capacity-soft-warn:inv-start");
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps the default hard Settings toast and typed capacity error", async () => {
    fetchMock.mockResolvedValue({
      ok: false, status: 429,
      text: async () => JSON.stringify({ detail: exhaustion }),
    });

    await expect(startInvestigation(request)).rejects.toMatchObject({
      name: "CapacityExhaustedError", exhaustion,
    });
    expect(toast.err).toHaveBeenCalledWith(
      expect.stringContaining("10/10 ACU"),
      { ttl: 10000, target: { path: "/settings" } },
    );
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/investigations"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), credentials: "include",
    });
  });

  it("defers the hard explanation while retaining the same typed error and publisher", async () => {
    fetchMock.mockResolvedValue({
      ok: false, status: 429,
      text: async () => JSON.stringify({ detail: exhaustion }),
    });

    const error: unknown = await startInvestigation(request, { capacityEffects: "deferred" })
      .then(() => null, (reason: unknown) => reason);
    expect(error).toBeInstanceOf(CapacityExhaustedError);
    expect(toast.err).not.toHaveBeenCalled();
    if (!(error instanceof CapacityExhaustedError)) throw error;

    publishStartCapacityEffect({ kind: "hard", exhaustion: error.exhaustion });
    expect(toast.err).toHaveBeenCalledWith(
      expect.stringContaining("10/10 ACU"),
      { ttl: 10000, target: { path: "/settings" } },
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the default soft warning in the response, stash and toast", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ investigation_id: "inv-start", status: "started", start_event_id: "ev-start", capacity_warning: warning }),
    });

    const result = await startInvestigation(request);
    expect(result.capacity_warning).toEqual(warning);
    expect(takeCapacityWarning("inv-start")).toEqual(warning);
    expect(toast.warn).toHaveBeenCalledWith(
      expect.stringContaining("9/10 ACU"),
      { ttl: 8000, target: { path: "/inv/inv-start" } },
    );
  });

  it("returns the soft warning without publishing until the caller admits it", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ investigation_id: "inv-start", status: "started", start_event_id: "ev-start", capacity_warning: warning }),
    });

    const result = await startInvestigation(request, { capacityEffects: "deferred" });
    expect(result.capacity_warning).toEqual(warning);
    expect(takeCapacityWarning("inv-start")).toBeNull();
    expect(toast.warn).not.toHaveBeenCalled();
    if (!result.capacity_warning) throw new Error("Expected parsed unit warning");

    publishStartCapacityEffect({ kind: "soft", investigationId: result.investigation_id, warning: result.capacity_warning });
    expect(takeCapacityWarning("inv-start")).toEqual(warning);
    expect(toast.warn).toHaveBeenCalledWith(
      expect.stringContaining("9/10 ACU"),
      { ttl: 8000, target: { path: "/inv/inv-start" } },
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps an inadmissible deferred response free of helper capacity effects", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        investigation_id: "inv-start", status: "unexpected", start_event_id: "",
        operation_id: "wrong-operation", capacity_warning: warning,
      }),
    });

    const result = await startInvestigation(request, { capacityEffects: "deferred" });
    expect(result).toMatchObject({
      investigation_id: "inv-start", status: "unexpected", start_event_id: "",
      operation_id: "wrong-operation", capacity_warning: warning,
    });
    expect(toast.err).not.toHaveBeenCalled();
    expect(toast.warn).not.toHaveBeenCalled();
    expect(takeCapacityWarning("inv-start")).toBeNull();
  });

  it("keeps default and deferred wire and non-capacity ApiError identical", async () => {
    const body = JSON.stringify({ detail: { code: "provider_upstream_error" } });
    fetchMock.mockResolvedValue({ ok: false, status: 503, text: async () => body });

    const defaultError: unknown = await startInvestigation(request)
      .then(() => null, (reason: unknown) => reason);
    const deferredError: unknown = await startInvestigation(request, { capacityEffects: "deferred" })
      .then(() => null, (reason: unknown) => reason);

    expect(defaultError).toBeInstanceOf(ApiError);
    expect(deferredError).toBeInstanceOf(ApiError);
    expect(defaultError).toMatchObject({
      message: "POST /investigations failed: HTTP 503", status: 503, body,
    });
    expect(deferredError).toMatchObject({
      message: "POST /investigations failed: HTTP 503", status: 503, body,
    });
    expect(fetchMock.mock.calls).toHaveLength(2);
    expect(fetchMock.mock.calls[0]).toEqual(fetchMock.mock.calls[1]);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining("/investigations"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), credentials: "include",
    });
    expect(toast.err).not.toHaveBeenCalled();
    expect(toast.warn).not.toHaveBeenCalled();
  });
});
