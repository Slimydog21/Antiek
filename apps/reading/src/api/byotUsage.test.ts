import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../lib/api";
import { fetchKeyBalance, fetchUsageSnapshot, setKeyLimit } from "./byotUsage";

vi.mock("../lib/api", () => ({ API_BASE: "/api", apiFetch: vi.fn() }));

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const usage = { api_key_id: "user-model-1", used_cents: 125, limit_cents: 500, remaining_cents: 375, held_cents: 75, available_cents: 300 };
const balance = {
  api_key_id: "user-model-1",
  catalog_id: "deepseek",
  kind: "balance_native",
  balance_usd: 23.5,
  granted_usd: 30,
  spend_usd: null,
  budget_usd: null,
  utilization: null,
  window_label: null,
  resets_at: null,
  note: null,
  held_cents: 75,
  available_cents: 300,
};

describe("BYOT usage API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads owner usage and balance through exact paths", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(response({ keys: [usage], count: 1 }))
      .mockResolvedValueOnce(response(balance));
    await expect(fetchUsageSnapshot()).resolves.toEqual({ keys: [usage], count: 1 });
    await expect(fetchKeyBalance("user-model-1")).resolves.toEqual(balance);
    expect(apiFetch).toHaveBeenNthCalledWith(1, "/api/settings/usage");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/api/settings/balance/user-model-1");
  });

  it("sets and clears integer-cent limits", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response(usage));
    await setKeyLimit("user-model-1", 500);
    expect(apiFetch).toHaveBeenCalledWith("/api/settings/usage/user-model-1/limit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit_cents: 500 }),
    });
  });

  it.each([-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1])(
    "rejects an unsafe limit before transport",
    async (limit) => {
      await expect(setKeyLimit("user-model-1", limit)).rejects.toThrow("usage API request is invalid");
      expect(apiFetch).not.toHaveBeenCalled();
    },
  );

  it.each(["", " padded ", "x".repeat(257)])("rejects an unsafe key id before transport", async (keyId) => {
    await expect(setKeyLimit(keyId, 100)).rejects.toThrow("usage API request is invalid");
    await expect(fetchKeyBalance(keyId)).rejects.toThrow("balance API request is invalid");
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it.each([
    { keys: [{ ...usage, api_key: "secret" }], count: 1 },
    { keys: [{ ...usage, remaining_cents: 499 }], count: 1 },
    { keys: [{ ...usage, available_cents: 375 }], count: 1 },
    { keys: [{ ...usage, held_cents: 376, available_cents: 0 }], count: 1 },
    { keys: [{ ...usage, used_cents: Number.POSITIVE_INFINITY }], count: 1 },
    { keys: [usage], count: 2 },
  ])("rejects contradictory or secret-shaped usage payloads", async (body) => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response(body));
    await expect(fetchUsageSnapshot()).rejects.toThrow("usage API returned an invalid response");
  });

  it.each([
    { ...balance, secret: "must-not-pass" },
    { ...balance, utilization: 1.1 },
    { ...balance, balance_usd: -1 },
    { ...balance, kind: "invented" },
    { ...balance, resets_at: 1.5 },
    { ...balance, held_cents: -1 },
    { ...balance, available_cents: Number.MAX_SAFE_INTEGER + 1 },
  ])("rejects unsafe balance metadata", async (body) => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response(body));
    await expect(fetchKeyBalance("user-model-1")).rejects.toThrow("balance API returned an invalid response");
  });

  it.each([
    { ...balance, kind: "balance_native", spend_usd: 1 },
    { ...balance, kind: "spend_history", balance_usd: null, granted_usd: null, spend_usd: 1, window_label: "month" },
    { ...balance, kind: "quota_pct", balance_usd: null, granted_usd: null, utilization: 0.5, window_label: null },
    { ...balance, kind: "meter_only", balance_usd: null, granted_usd: null, spend_usd: null },
    { ...balance, kind: "unavailable", balance_usd: 0, granted_usd: null },
  ])("rejects fields that contradict the balance authority kind", async (body) => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response(body));
    await expect(fetchKeyBalance("user-model-1")).rejects.toThrow("balance API returned an invalid response");
  });

  it("rejects cents and timestamps outside JavaScript's exact integer range", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response({
      keys: [{ ...usage, used_cents: Number.MAX_SAFE_INTEGER + 1 }], count: 1,
    }));
    await expect(fetchUsageSnapshot()).rejects.toThrow("usage API returned an invalid response");

    vi.mocked(apiFetch).mockResolvedValueOnce(response({
      ...balance,
      kind: "quota_pct",
      balance_usd: null,
      granted_usd: null,
      utilization: 0.5,
      window_label: "monthly",
      resets_at: Number.MAX_SAFE_INTEGER + 1,
    }));
    await expect(fetchKeyBalance("user-model-1")).rejects.toThrow("balance API returned an invalid response");
  });

  it("rejects a timestamp outside the JavaScript Date range", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response({
      ...balance,
      kind: "quota_pct",
      balance_usd: null,
      granted_usd: null,
      utilization: 0.5,
      window_label: "monthly",
      resets_at: 8_640_000_000_001,
    }));
    await expect(fetchKeyBalance("user-model-1")).rejects.toThrow("balance API returned an invalid response");
  });

  it("rejects a snapshot whose aggregate cents are not exact", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response({
      keys: [
        { ...usage, api_key_id: "a", used_cents: Number.MAX_SAFE_INTEGER, limit_cents: null, remaining_cents: null, held_cents: 0, available_cents: null },
        { ...usage, api_key_id: "b", used_cents: 1, limit_cents: null, remaining_cents: null, held_cents: 0, available_cents: null },
      ],
      count: 2,
    }));
    await expect(fetchUsageSnapshot()).rejects.toThrow("usage API returned an invalid response");
  });

  it("never includes a server response body in errors", async () => {
    const secret = "provider-secret-sentinel";
    vi.mocked(apiFetch).mockResolvedValueOnce(response({ detail: secret }, 503));
    let message = "";
    try { await fetchUsageSnapshot(); } catch (error) { message = error instanceof Error ? error.message : String(error); }
    expect(message).toBe("usage API 503");
    expect(message).not.toContain(secret);
  });
});
