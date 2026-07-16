import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import { approveFallbackReceipt, fetchFallbackReceiptHistory } from "./settings";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function history() {
  return {
    authority: "read_only_fallback_receipt_history",
    next_cursor: "next-page",
    items: [
      {
        chain_id: "chain-a",
        manifest_sha256: "a".repeat(64),
        outcome: "settled",
        created_at: "2026-07-16T10:00:00Z",
        currency: "USD",
        ceiling_cents: 100,
        maximum_chain_exposure_cents: 20,
        approval_eligible: false,
        approval_id: `fallback-approval:${"d".repeat(64)}`,
        approved_at: "2026-07-16T09:59:00Z",
        routes: [
          {
            fallback_index: 0,
            provider: "zai",
            model: "glm-5.2",
            seam_id: "user.prompt.generate",
            operation: "generate",
            projected_max_cents: 20,
            state: "settled",
            actual_cents: 12,
            resolved_at: "2026-07-16T10:01:00Z",
            settlement_evidence_sha256: "b".repeat(64),
            settlement_intent_sha256: "c".repeat(64),
          },
        ],
      },
    ],
  };
}

beforeEach(() => mockFetch.mockReset());

describe("fetchFallbackReceiptHistory", () => {
  it("requests bounded keyset pages and accepts a consistent receipt", async () => {
    mockFetch.mockResolvedValue(response(history()));

    const result = await fetchFallbackReceiptHistory("opaque cursor");

    expect(result.items[0].routes[0].actual_cents).toBe(12);
    expect(mockFetch).toHaveBeenCalledWith(
      "/settings/fallback-receipts?limit=20&cursor=opaque+cursor",
    );
  });

  it("rejects unexpected fields and contradictory state", async () => {
    const leaked = history();
    Object.assign(leaked.items[0], { owner_id: "private" });
    mockFetch.mockResolvedValueOnce(response(leaked));
    await expect(fetchFallbackReceiptHistory()).rejects.toThrow(
      "unexpected fields",
    );

    const contradictory = history();
    contradictory.items[0].routes[0].state = "released";
    mockFetch.mockResolvedValueOnce(response(contradictory));
    await expect(fetchFallbackReceiptHistory()).rejects.toThrow(
      "contradicts its state",
    );

    const impossibleDate = history();
    impossibleDate.items[0].approved_at = "2026-02-30T09:59:00Z";
    mockFetch.mockResolvedValueOnce(response(impossibleDate));
    await expect(fetchFallbackReceiptHistory()).rejects.toThrow(
      "fallback receipt chain is invalid",
    );
  });

  it("returns a value-free HTTP failure", async () => {
    mockFetch.mockResolvedValue(response({ detail: "private path" }, 503));

    await expect(fetchFallbackReceiptHistory()).rejects.toThrow(
      "fallback receipt history API 503",
    );
  });
});

describe("approveFallbackReceipt", () => {
  it("posts exact preview terms and accepts only the matching receipt", async () => {
    const body = history();
    const chain = {
      ...body.items[0],
      currency: "USD" as const,
      outcome: "unattempted" as const,
      approval_id: null,
      approved_at: null,
      approval_eligible: true,
      routes: [{
        ...body.items[0].routes[0],
        state: "unattempted" as const,
        actual_cents: null,
        resolved_at: null,
        settlement_evidence_sha256: null,
        settlement_intent_sha256: null,
      }],
    };
    mockFetch.mockResolvedValue(response({
      authority: "durable_fallback_spend_approval",
      approval_id: `fallback-approval:${"e".repeat(64)}`,
      chain_id: "chain-a",
      manifest_sha256: "a".repeat(64),
      currency: "USD",
      ceiling_cents: 100,
      maximum_chain_exposure_cents: 20,
      approved_at: "2026-07-16T11:00:00Z",
    }));

    const receipt = await approveFallbackReceipt(chain);

    expect(receipt.approval_id).toBe(`fallback-approval:${"e".repeat(64)}`);
    expect(mockFetch).toHaveBeenCalledWith(
      "/settings/fallback-receipts/chain-a/approval",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_manifest_sha256: "a".repeat(64),
          expected_ceiling_cents: 100,
        }),
      },
    );
  });

  it("rejects substituted approval terms", async () => {
    const body = history();
    const chain = {
      ...body.items[0],
      currency: "USD" as const,
      outcome: "unattempted" as const,
      approval_id: null,
      approved_at: null,
      approval_eligible: true,
      routes: [{
        ...body.items[0].routes[0], state: "unattempted" as const,
        actual_cents: null, resolved_at: null,
        settlement_evidence_sha256: null, settlement_intent_sha256: null,
      }],
    };
    mockFetch.mockResolvedValue(response({
      authority: "durable_fallback_spend_approval",
      approval_id: `fallback-approval:${"e".repeat(64)}`,
      chain_id: "chain-other",
      manifest_sha256: "a".repeat(64),
      currency: "USD",
      ceiling_cents: 100,
      maximum_chain_exposure_cents: 20,
      approved_at: "2026-07-16T11:00:00Z",
    }));

    await expect(approveFallbackReceipt(chain)).rejects.toThrow(
      "does not match exact terms",
    );

    mockFetch.mockResolvedValue(response({
      authority: "durable_fallback_spend_approval",
      approval_id: `fallback-approval:${"e".repeat(64)}`,
      chain_id: "chain-a",
      manifest_sha256: "a".repeat(64),
      currency: "USD",
      ceiling_cents: 100,
      maximum_chain_exposure_cents: 20,
      approved_at: "2026-02-30T11:00:00Z",
    }));
    await expect(approveFallbackReceipt(chain)).rejects.toThrow(
      "does not match exact terms",
    );
  });
});
