/**
 * SPR-02 ANT-AUTH-DIAG — requestMagicLink diagnostic taxonomy.
 *
 * `fetch` is mocked (no network). Test names cite matrix failure_id.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AUTH_TRANSPORT_FETCH_MESSAGE,
  authCallbackDiagnosticCode,
  authCallbackErrorDisplay,
  authLoginErrorDisplay,
  requestMagicLink,
  stripAuthCallbackErrorParam,
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
      jsonResponse(200, { sent: true }),
    );
    const result = await requestMagicLink("any@example.com");
    expect(result).toEqual({ kind: "sent", diagnostic_code: null, layer: null });
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

describe("authCallbackErrorDisplay", () => {
  it.each([
    [
      "magic_link_expired",
      "This sign-in link expired.",
      "B-POLICY-CALLBACK-EXPIRED",
    ],
    [
      "magic_link_invalid",
      "This sign-in link is not valid.",
      "B-POLICY-CALLBACK-INVALID",
    ],
    [
      "not_authorized",
      "This email is not authorized for Antiek.",
      "B-POLICY-CALLBACK-NOT-AUTH",
    ],
  ] as const)(
    "SPR-03 closed callback error %s maps to copy and diagnostic code",
    (callbackCode, message, diagnosticCode) => {
      expect(authCallbackErrorDisplay(callbackCode)).toMatchObject({ message });
      expect(authCallbackDiagnosticCode(callbackCode)).toBe(diagnosticCode);
    },
  );

  it("ignores unknown callback errors instead of inventing UI copy", () => {
    expect(authCallbackErrorDisplay("unexpected")).toBeNull();
    expect(authCallbackDiagnosticCode("unexpected")).toBeNull();
  });
});

describe("stripAuthCallbackErrorParam", () => {
  it("removes callback error while preserving next", () => {
    const next = stripAuthCallbackErrorParam(
      new URLSearchParams("error=magic_link_expired&next=%2Finv%2Fabc"),
    );
    expect(next).toBe("next=%2Finv%2Fabc");
  });

  it("returns empty search when error was the only param", () => {
    expect(stripAuthCallbackErrorParam(new URLSearchParams("error=not_authorized"))).toBe(
      "",
    );
  });
});
