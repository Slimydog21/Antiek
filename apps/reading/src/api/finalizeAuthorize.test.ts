import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  FinalizeAuthorizeHttpError,
  formatAuthorizeResult,
  parseFinalizeAuthorizeResult,
  postFinalizeAuthorize,
} from "./finalizeAuthorize";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("parseFinalizeAuthorizeResult", () => {
  it("accepts strict authorized true when operator accepted", () => {
    const r = parseFinalizeAuthorizeResult(
      {
        authorized: true,
        draft_id: "d1",
        parent_asset_id: "p1",
        reason: "ok",
        notes: ["authorized: provisional draft accepted by operator"],
      },
      { operator_accepted: true },
    );
    expect(r.authorized).toBe(true);
    expect(formatAuthorizeResult(r)).toMatch(/AUTHORIZED/i);
  });

  it("forces authorized=false when operator_accepted not true even if body says true", () => {
    const r = parseFinalizeAuthorizeResult(
      {
        authorized: true,
        draft_id: "d1",
        parent_asset_id: "p1",
        reason: "ok",
        notes: [],
      },
      { operator_accepted: false },
    );
    expect(r.authorized).toBe(false);
    expect(r.reason).toBe("operator_accept_required");
  });

  it("rejects non-boolean authorized", () => {
    expect(() =>
      parseFinalizeAuthorizeResult({
        authorized: "yes",
        draft_id: "d",
        parent_asset_id: "p",
        reason: "ok",
        notes: [],
      }),
    ).toThrow(/authorized must be boolean/);
  });
});

describe("postFinalizeAuthorize", () => {
  it("POSTs and returns denied without accept", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        authorized: false,
        draft_id: "d1",
        parent_asset_id: "p1",
        reason: "operator_accept_required",
        notes: ["explicit operator_accepted=true required"],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postFinalizeAuthorize({
      draft_id: "d1",
      parent_asset_id: "p1",
      provisional: true,
      operator_accepted: false,
    });
    expect(body.authorized).toBe(false);
    expect(mockFetch).toHaveBeenCalledWith(
      "/twins/finalize/authorize",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("client fail-closed if server wrongly returns authorized without accept", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        authorized: true,
        draft_id: "d1",
        parent_asset_id: "p1",
        reason: "ok",
        notes: [],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postFinalizeAuthorize({
      draft_id: "d1",
      parent_asset_id: "p1",
      provisional: true,
      operator_accepted: false,
    });
    expect(body.authorized).toBe(false);
  });

  it("rejects empty ids without network", async () => {
    await expect(
      postFinalizeAuthorize({
        draft_id: " ",
        parent_asset_id: "p",
        provisional: true,
        operator_accepted: true,
      }),
    ).rejects.toThrow(/draft_id/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postFinalizeAuthorize({
        draft_id: "d",
        parent_asset_id: "p",
        provisional: true,
        operator_accepted: true,
      }),
    ).rejects.toBeInstanceOf(FinalizeAuthorizeHttpError);
  });
});

describe("immutability", () => {
  it("does not mutate frozen response notes when fail-closing authorized", () => {
    const notes = Object.freeze(["server note"]) as unknown as string[];
    const body = {
      authorized: true,
      draft_id: "d1",
      parent_asset_id: "p1",
      reason: "ok",
      notes,
    };
    const r = parseFinalizeAuthorizeResult(body, { operator_accepted: false });
    expect(r.authorized).toBe(false);
    expect([...notes]).toEqual(["server note"]);
    expect(r.notes.some((n) => /client fail-closed/i.test(n))).toBe(true);
  });
});
