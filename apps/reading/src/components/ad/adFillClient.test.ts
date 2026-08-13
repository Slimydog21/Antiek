import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));
import { apiFetch } from "../../lib/api";
import { fetchFill } from "./adFillClient";

const mockedFetch = vi.mocked(apiFetch);

describe("ad fill authority client", () => {
  beforeEach(() => mockedFetch.mockReset());

  it("sends one server-priced multi-edge request with no client price", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({
      window_id: "win:read:a", fills: [{ fill_decision_id: "fd-1", slot_id: "slot-1", position: "top", kind: "house", house: null, ad: null, price_status: "unpriced", revenue_usd_cents: 0 }],
    }), { status: 200 }));
    const result = await fetchFill({ windowId: "win:read:a", lens: "read", positions: ["top"] });
    const init = mockedFetch.mock.calls[0][1]!;
    expect(mockedFetch.mock.calls[0][0]).toBe("/api/ad/fills");
    expect(JSON.parse(String(init.body))).toEqual({
      window_id: "win:read:a", lens: "read", positions: ["top"], document_id: null, page_index: null,
    });
    expect(String(init.body)).not.toContain("revenue");
    expect(result.served).toBe(true);
  });

  it("fails closed to house when the server returns another window", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({ window_id: "wrong", fills: [] }), { status: 200 }));
    const result = await fetchFill({ windowId: "win:read:a", lens: "read", positions: ["top", "bottom"] });
    expect(result.served).toBe(false);
    expect(result.fills.every((fill) => fill.kind === "house" && fill.revenue_usd_cents === 0)).toBe(true);
  });

  it("rejects undeclared fields and any server claim of priced revenue", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({
      window_id: "win:read:a",
      fills: [{ fill_decision_id: "fd-1", slot_id: "slot-1", position: "top", kind: "ad", ad: null, house: null, price_status: "settled", revenue_usd_cents: 9, billing_token: "never-trust" }],
    }), { status: 200 }));
    const result = await fetchFill({ windowId: "win:read:a", lens: "read", positions: ["top"] });
    expect(result).toEqual({
      served: false,
      fills: [{ fill_decision_id: "local-house", slot_id: "local:top", position: "top", kind: "house", ad: null, house: null, revenue_usd_cents: 0, price_status: "unpriced" }],
    });
  });

  it("rejects missing edges and unsafe or incoherent nested creatives", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({
      window_id: "win:read:a",
      fills: [{
        fill_decision_id: "fd-1", slot_id: "slot-1", position: "top", kind: "ad",
        ad: { inventory_id: "ad-1", advertiser_display_name: "Example", creative_url: "https://cdn.example/ad.png", landing_url: "javascript:alert(1)" },
        house: null, price_status: "unpriced", revenue_usd_cents: 0,
      }],
    }), { status: 200 }));
    const result = await fetchFill({ windowId: "win:read:a", lens: "read", positions: ["top", "bottom"] });
    expect(result.served).toBe(false);
    expect(result.fills).toHaveLength(2);
    expect(result.fills.every((fill) => fill.kind === "house")).toBe(true);
  });
});
