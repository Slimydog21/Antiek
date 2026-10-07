// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ apiFetch: request }));

import { assembleDraft, whatEveryoneAgreesOn } from "./speakApi";

beforeEach(() => request.mockReset());

describe.each([
  ["comparison", () => whatEveryoneAgreesOn("test-project")],
  ["assembly", () => assembleDraft("test-project", false)],
] as const)("Speak %s refusal", (_action, run) => {
  it.each([
    [401, "operator_auth_required"],
    [503, "provider unavailable"],
  ])("retains HTTP %s and the actual string reason", async (status, detail) => {
    request.mockResolvedValue(new Response(JSON.stringify({ detail }), { status }));
    await expect(run()).rejects.toThrow(`HTTP ${status}: ${detail}`);
  });

  it("retains the status when an error page is not JSON", async () => {
    request.mockResolvedValue(new Response("upstream unavailable", { status: 503 }));
    await expect(run()).rejects.toThrow("HTTP 503");
  });

  it("does not stringify structured diagnostics into a guessed cause", async () => {
    request.mockResolvedValue(new Response(JSON.stringify({ detail: { reason: "refused" } }), { status: 403 }));
    await expect(run()).rejects.toThrow(/^HTTP 403$/);
  });
});
