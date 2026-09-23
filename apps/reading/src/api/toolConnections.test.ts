import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../lib/api";
import {
  fetchToolConnections,
  removeToolConnection,
  saveToolConnection,
} from "./toolConnections";

vi.mock("../lib/api", () => ({ API_BASE: "/api", apiFetch: vi.fn() }));

const row = {
  vendor: "youtube",
  display_name: "YouTube Data API",
  credential_kind: "api_key",
  auth: "api_key_query",
  docs_url: "https://example.test/youtube",
  status: "configured_unverified",
  credential_present: true,
  status_note: null,
  searchable: true,
  quota: {
    kind: "youtube_units",
    remaining: 9900,
    limit: 10000,
    reset_at: "2026-08-13T00:00:00-07:00",
    hard_exhausted: false,
    note: "Local Antiek meter",
    estimated_cost_usd: null,
    cost_note: null,
  },
} as const;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("toolConnections API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("accepts the paste-key vendors the catalog lists but nothing calls yet", async () => {
    // A vendor missing from the client's allowlist throws in parseConnection,
    // which takes down the whole settings panel, not just that row.
    const fred = {
      ...row,
      vendor: "fred",
      display_name: "FRED (St. Louis Fed)",
      docs_url: "https://fred.stlouisfed.org/docs/api/api_key.html",
      searchable: false,
      quota: {
        kind: "rate_ceiling",
        remaining: null,
        limit: 100,
        reset_at: null,
        hard_exhausted: null,
        note: "Antiek's own per-account brake on your key: 100 requests per minute. It is not a provider allowance.",
        estimated_cost_usd: null,
        cost_note: null,
      },
    };
    const alphaVantage = { ...fred, vendor: "alpha_vantage", display_name: "Alpha Vantage" };
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({ connections: [fred, alphaVantage], count: 2 }));
    const parsed = await fetchToolConnections();
    expect(parsed.map((item) => [item.vendor, item.searchable])).toEqual([
      ["fred", false],
      ["alpha_vantage", false],
    ]);
  });

  it("reads an exact allowlisted inventory", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({ connections: [row], count: 1 }));
    await expect(fetchToolConnections()).resolves.toEqual([row]);
    expect(apiFetch).toHaveBeenCalledWith("/api/settings/tools");
  });

  it("sends a write-only credential and never includes error-body text", async () => {
    const secret = "AIza-secret-sentinel";
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse(row));
    await saveToolConnection("youtube", secret);
    expect(apiFetch).toHaveBeenCalledWith("/api/settings/tools/youtube", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: secret }),
    });

    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({ detail: secret }, 422));
    let message = "";
    try {
      await saveToolConnection("youtube", secret);
    } catch (error) {
      message = error instanceof Error ? error.message : String(error);
    }
    expect(message).toBe("Tool settings API 422");
    expect(message).not.toContain(secret);
  });

  it("rejects unexpected response fields, including secret-shaped additions", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({
      connections: [{ ...row, api_key: "must-not-pass" }],
      count: 1,
    }));
    await expect(fetchToolConnections()).rejects.toThrow("invalid connection response");
  });

  it.each([
    { ...row, docs_url: "javascript:alert(1)" },
    { ...row, status: "unconfigured", credential_present: true },
    { ...row, status: "configured_unverified", credential_present: false },
    { ...row, quota: { ...row.quota, remaining: -1 } },
    { ...row, quota: { ...row.quota, remaining: 10001 } },
    { ...row, quota: { ...row.quota, remaining: "Infinity" } },
    { ...row, quota: { ...row.quota, reset_at: "not-a-date" } },
    { ...row, quota: { ...row.quota, hard_exhausted: true, remaining: 1 } },
  ])("rejects contradictory or unsafe connection metadata", async (invalidRow) => {
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({
      connections: [invalidRow],
      count: 1,
    }));
    await expect(fetchToolConnections()).rejects.toThrow(/invalid (connection|quota) response/);
  });

  it("rejects kind-specific quota fields", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({
      connections: [{
        ...row,
        quota: {
          kind: "unavailable",
          remaining: null,
          limit: 100,
          reset_at: null,
          hard_exhausted: null,
          note: null,
          estimated_cost_usd: null,
          cost_note: null,
        },
      }],
      count: 1,
    }));
    await expect(fetchToolConnections()).rejects.toThrow("invalid quota response");
  });

  it("deletes the exact allowlisted vendor path", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse({ removed: "youtube" }));
    await removeToolConnection("youtube");
    expect(apiFetch).toHaveBeenCalledWith("/api/settings/tools/youtube", { method: "DELETE" });
  });
});
