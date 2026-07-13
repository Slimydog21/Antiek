/**
 * SPR-02 ANT-AUTH-DIAG — requestMagicLink diagnostic taxonomy.
 *
 * `fetch` is mocked (no network). Test names cite matrix failure_id.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AUTH_TRANSPORT_FETCH_MESSAGE,
  authLoginErrorDisplay,
  requestMagicLink,
} from "./auth";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("requestMagicLink", () => {
  it("A-TRANSPORT-FETCH: fetch reject yields Cannot reach Antiek API (not Failed to fetch)", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new TypeError("Failed to fetch"),
    );
    const result = await requestMagicLink("probe@example.com");
    expect(result).toEqual({
      kind: "error",
      code: "transport_fetch_failed",
      message: AUTH_TRANSPORT_FETCH_MESSAGE,
      diagnostic_code: "A-TRANSPORT-FETCH",
      layer: "A",
    });
    expect(result.kind === "error" && result.message).not.toContain("Failed to fetch");
  });

  it("B-POLICY-ALLOWLIST-SILENT: 200 sent has null diagnostic_code", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(200, { sent: true, attempt_id: "attempt-123456789", claim_secret: "claim-1234567890", device_code: "2048" }),
    );
    const result = await requestMagicLink("any@example.com");
    expect(result).toEqual({
      kind: "sent",
      attempt_id: "attempt-123456789",
      claim_secret: "claim-1234567890",
      device_code: "2048",
      diagnostic_code: null,
      layer: null,
    });
  });

  it("B-POLICY-EMAIL-503: HTTP 503 maps to B-POLICY-EMAIL-503 layer B", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(503, {
        detail: { code: "email_delivery_failed", message: "Resend API error" },
      }),
    );
    const result = await requestMagicLink("operator@example.com");
    expect(result).toMatchObject({
      kind: "error",
      code: "email_delivery_failed",
      message: "Resend API error",
      diagnostic_code: "B-POLICY-EMAIL-503",
      layer: "B",
    });
  });
});

describe("authLoginErrorDisplay", () => {
  it("A-TRANSPORT-FETCH: Login hint mentions VPN and curl discriminant", () => {
    const copy = authLoginErrorDisplay({
      kind: "error",
      code: "transport_fetch_failed",
      message: AUTH_TRANSPORT_FETCH_MESSAGE,
      diagnostic_code: "A-TRANSPORT-FETCH",
      layer: "A",
    });
    expect(copy.message).toBe("Cannot reach Antiek API");
    expect(copy.hint).toMatch(/VPN/i);
    expect(copy.hint).toMatch(/curl/i);
  });

  it("B-POLICY-EMAIL-503: Login hint mentions Resend or AgentMail", () => {
    const copy = authLoginErrorDisplay({
      kind: "error",
      code: "email_delivery_failed",
      message: "Resend API error",
      diagnostic_code: "B-POLICY-EMAIL-503",
      layer: "B",
    });
    expect(copy.message).toBe("Resend API error");
    expect(copy.hint).toMatch(/Resend|AgentMail/i);
  });
});
