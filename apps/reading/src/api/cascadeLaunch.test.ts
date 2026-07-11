import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  CascadeLaunchClientError,
  CascadeLaunchHttpError,
  normalizeSourcePolicy,
  postCascadeLaunch,
} from "./cascadeLaunch";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("normalizeSourcePolicy", () => {
  it("dedupes and rejects unknown or blank entries", () => {
    expect(normalizeSourcePolicy(["arxiv", "arxiv", "web"])).toEqual([
      "arxiv",
      "web",
    ]);
    expect(normalizeSourcePolicy([])).toBeNull();
    expect(normalizeSourcePolicy(null)).toBeNull();
    expect(() => normalizeSourcePolicy(["arxiv", "ftp"])).toThrow(
      /source_policy_invalid|unknown/,
    );
    expect(() => normalizeSourcePolicy(["arxiv", " "])).toThrow(
      /blank|source_policy_invalid/,
    );
  });
});

describe("postCascadeLaunch", () => {
  it("rejects require_source_preflight without policy before network", async () => {
    await expect(
      postCascadeLaunch({
        root_id: "root-1",
        require_source_preflight: true,
      }),
    ).rejects.toMatchObject({ code: "source_policy_required" });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("POSTs launch with source_policy and requires receipt when required", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        launched: true,
        handles: [],
        source_preflight: {
          source_policy: ["arxiv", "substack"],
          source_receipt_id: "rcpt-1",
        },
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postCascadeLaunch({
      root_id: "root-1",
      source_policy: ["arxiv", "substack"],
      require_source_preflight: true,
      per_research_budget_usd: 0.25,
    });
    expect(body.source_policy).toEqual(["arxiv", "substack"]);
    expect(body.source_preflight?.source_receipt_id).toBe("rcpt-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/research/plans/root-1/launch",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("fails closed when required launch omits source_preflight", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ launched: true, handles: [] }),
      text: async () => "",
    } as unknown as Response);
    await expect(
      postCascadeLaunch({
        root_id: "root-1",
        source_policy: ["web"],
        require_source_preflight: true,
      }),
    ).rejects.toMatchObject({ code: "source_preflight_missing" });
  });

  it("rejects empty root_id and nonpositive budget without network", async () => {
    await expect(
      postCascadeLaunch({ root_id: "  " }),
    ).rejects.toBeInstanceOf(CascadeLaunchClientError);
    await expect(
      postCascadeLaunch({ root_id: "r", per_research_budget_usd: 0 }),
    ).rejects.toMatchObject({ code: "budget_invalid" });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      text: async () =>
        JSON.stringify({ detail: { code: "source_policy_unavailable" } }),
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postCascadeLaunch({
        root_id: "r",
        source_policy: ["web"],
      }),
    ).rejects.toBeInstanceOf(CascadeLaunchHttpError);
  });
});
