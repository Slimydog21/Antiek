import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  approveMidnightOilCeiling,
  createMidnightOilJob,
  getMidnightOilJob,
  issueMidnightOilSpendConsent,
  resetMidnightOilSpendConsent,
} from "./midnightOil";

const mockFetch = vi.fn();

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => mockFetch(...args),
}));

describe("midnightOil API client", () => {
  beforeEach(() => mockFetch.mockReset());

  it("createMidnightOilJob posts goals + duration", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
      }),
    });
    const out = await createMidnightOilJob({
      goals: ["g"],
      duration_minutes: 60,
    });
    expect(out.recommended_price_ceiling_usd).toBe(3.6);
    expect(out.view_format).toBe("html");
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/create",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("approveMidnightOilCeiling keeps consent ephemeral and enqueues by header", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token: "ephemeral-consent-token",
          operation_id: "op_1",
          ceiling_cents: 360,
          issued_at_ms: 10,
          expires_at_ms: 20,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "moil_1", operation_id: "op_1", state: "queued" }),
      })
      .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
      }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema_version: 1,
          job_id: "moil_1",
          operation_id: "op_1",
          state: "queued",
          terminal_outcome: null,
          approved_ceiling_cents: 360,
          confirmed_spent_cents: 0,
          reserved_cents: 0,
          unknown_outcome: false,
          remaining_cents: 360,
          cost_state: "not_reserved",
          consent_expires_at_ms: 20,
          enqueued_at_ms: 11,
          lease_expires_at_ms: null,
          completed_at_ms: null,
          deposit_document_id: null,
          deposit_href: null,
          graph_deliverable_id: null,
          graph_deep_links: [],
          operator_action: "wait_for_worker",
          view_format: "html",
        }),
      });
    const out = await approveMidnightOilCeiling({
      job_id: "moil_1",
      use_recommended: true,
    });
    expect(out.runnable).toBe(false);
    expect(out.status).toBe("queued");
    expect(out.lifecycle?.state).toBe("queued");
    expect(mockFetch.mock.calls[0][0]).toBe(
      "/midnight-oil/jobs/moil_1/spend-consent",
    );
    const consentBody = String(mockFetch.mock.calls[0][1]?.body || "");
    expect(consentBody).not.toContain("ephemeral-consent-token");
    expect(mockFetch.mock.calls[1][0]).toBe("/midnight-oil/run");
    expect(mockFetch.mock.calls[1][1]?.headers).toEqual(
      expect.objectContaining({
        "X-Midnight-Oil-Spend-Consent": "ephemeral-consent-token",
      }),
    );
    expect(String(mockFetch.mock.calls[1][1]?.body)).not.toContain(
      "ephemeral-consent-token",
    );
    expect(JSON.stringify(out)).not.toContain("ephemeral-consent-token");
  });

  it("getMidnightOilJob fetches by id", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "approved",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: true,
      }),
    });
    const out = await getMidnightOilJob("moil_1");
    expect(out.job_id).toBe("moil_1");
    expect(mockFetch.mock.calls[0][0]).toBe("/midnight-oil/jobs/moil_1");
  });

  it("rejects sub-cent ceilings before issuing spend authority", async () => {
    await expect(
      issueMidnightOilSpendConsent({
        job_id: "moil_1",
        ceiling_usd: 1.005,
      }),
    ).rejects.toThrow(/at most two decimals/i);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("resets only the owner-authenticated unqueued consent authority", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        schema_version: 1,
        job_id: "moil_1",
        state: "consent_required",
        operation_state: "none",
        state_version: 2,
        operator_action: "issue_consent",
      }),
    });
    const out = await resetMidnightOilSpendConsent("moil_1");
    expect(out.state).toBe("consent_required");
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/jobs/moil_1/spend-consent",
      { method: "DELETE", cache: "no-store" },
    );
  });
});
