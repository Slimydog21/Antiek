import { describe, expect, it, vi } from "vitest";
import { apiFetch } from "../lib/api";
import {
  fetchSettingsBalance,
  fetchSettingsUsage,
  parseSettingsBalance,
  parseSettingsUsageSnapshot,
  setSettingsUsageLimit,
} from "./settingsUsage";

vi.mock("../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));

const usageBody = {
  keys: [
    {
      api_key_id: "user-deepseek",
      used_cents: 120,
      limit_cents: 1000,
      remaining_cents: 880,
      held_cents: 40,
      available_cents: 840,
    },
  ],
  count: 1,
};

const balanceBody = {
  api_key_id: "user-deepseek",
  catalog_id: "deepseek",
  kind: "balance_native",
  balance_usd: 42.5,
  granted_usd: 100,
  spend_usd: 57.5,
  budget_usd: null,
  utilization: null,
  window_label: null,
  resets_at: null,
  note: null,
  held_cents: 40,
  available_cents: 840,
};

describe("parseSettingsUsageSnapshot", () => {
  it("parses usage keys in server order", () => {
    const parsed = parseSettingsUsageSnapshot(usageBody);
    expect(parsed.count).toBe(1);
    expect(parsed.keys[0].api_key_id).toBe("user-deepseek");
    expect(parsed.keys[0].remaining_cents).toBe(880);
  });

  it.each([
    { keys: [], count: 1 },
    {
      keys: [
        {
          api_key_id: "user-deepseek",
          used_cents: 1,
          limit_cents: 2,
          remaining_cents: 1,
          held_cents: 0,
        },
      ],
      count: 1,
    },
    {
      keys: [
        {
          api_key_id: "user-deepseek",
          used_cents: -1,
          limit_cents: 2,
          remaining_cents: 1,
          held_cents: 0,
          available_cents: 1,
        },
      ],
      count: 1,
    },
  ])("rejects malformed usage payloads", (body) => {
    expect(() => parseSettingsUsageSnapshot(body)).toThrow(
      "Invalid settings usage response.",
    );
  });
});

describe("parseSettingsBalance", () => {
  it("parses a normalized live balance payload", () => {
    const parsed = parseSettingsBalance(balanceBody);
    expect(parsed.kind).toBe("balance_native");
    expect(parsed.balance_usd).toBeNull();
    expect(parsed.native_balances).toBeNull();
    expect(parsed.available_cents).toBe(840);
  });

  it("preserves each native currency and exact decimal string", () => {
    const native_balances = [
      { currency: "CNY", total: "12345678901234567890.0010", granted: "10.00", topped_up: "2.50" },
      { currency: "USD", total: "0.020", granted: "0.00", topped_up: "0.020" },
    ];
    const parsed = parseSettingsBalance({
      ...balanceBody, balance_usd: null, granted_usd: null, native_balances,
    });
    expect(parsed.native_balances).toEqual(native_balances);
    expect(parsed.balance_usd).toBeNull();
  });

  it("rejects malformed native balances", () => {
    for (const native_balances of [
    [{ currency: "CNY", total: 1.2, granted: "0", topped_up: "0" }],
    [{ currency: "cny", total: "1", granted: "0", topped_up: "0" }],
    [{ currency: "CNY", total: "1e3", granted: "0", topped_up: "0" }],
    [{ currency: "CNY", total: "01", granted: "0", topped_up: "0" }],
    [{ currency: "CNY", total: "1", granted: "0", topped_up: "0" }, { currency: "CNY", total: "2", granted: "0", topped_up: "0" }],
    [{ currency: "CNY", total: "1", granted: "0", topped_up: "0", extra: true }],
    Array.from({ length: 9 }, () => ({ currency: "CNY", total: "1", granted: "0", topped_up: "0" })),
    [],
    ]) {
      expect(() => parseSettingsBalance({ ...balanceBody, balance_usd: null, granted_usd: null, native_balances })).toThrow(
        "Invalid settings balance response.",
      );
    }
  });

  it("rejects DeepSeek native entries paired with legacy USD fields", () => {
    expect(() => parseSettingsBalance({
      ...balanceBody,
      native_balances: [{ currency: "CNY", total: "1", granted: "0", topped_up: "1" }],
    })).toThrow("Invalid settings balance response.");
  });

  it.each([
    {
      ...balanceBody,
      kind: "other",
    },
    {
      ...balanceBody,
      note: 123,
    },
    {
      ...balanceBody,
      api_key: "sk-should-never-appear",
    },
  ])("rejects invalid balance payloads", (body) => {
    expect(() => parseSettingsBalance(body)).toThrow(
      "Invalid settings balance response.",
    );
  });
});

describe("settingsUsage API calls", () => {
  it("fetches usage snapshot", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(
      new Response(JSON.stringify(usageBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await fetchSettingsUsage();
    expect(result.count).toBe(1);
    expect(vi.mocked(apiFetch)).toHaveBeenCalledWith("/settings/usage");
  });

  it("posts spend cap updates", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(
      new Response(JSON.stringify(usageBody.keys[0]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await setSettingsUsageLimit("user/deepseek", {
      limit_cents: 2000,
    });
    expect(result.limit_cents).toBe(1000);
    expect(vi.mocked(apiFetch)).toHaveBeenCalledWith(
      "/settings/usage/user%2Fdeepseek/limit",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit_cents: 2000 }),
      },
    );
  });

  it("fetches live balance", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(
      new Response(JSON.stringify(balanceBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await fetchSettingsBalance("user-deepseek");
    expect(result.kind).toBe("balance_native");
    expect(vi.mocked(apiFetch)).toHaveBeenCalledWith(
      "/settings/balance/user-deepseek",
    );
  });

  it("returns value-free http failures", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "internal details" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(fetchSettingsUsage()).rejects.toThrow(
      "Settings usage request failed (503). Check the values and try again.",
    );
  });
});
