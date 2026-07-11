import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  NotDiamondShadowHttpError,
  parseShadowHttpResult,
  postNotDiamondShadow,
} from "./notdiamondShadowHttp";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("parseShadowHttpResult", () => {
  it("requires authority shadow and discards invent while disabled", () => {
    const ok = parseShadowHttpResult({
      enabled: false,
      authority: "shadow",
      task: "general",
      local_model_id: "m1",
      nd_recommended_model_id: null,
      agreement: null,
      notes: [],
    });
    expect(ok.authority).toBe("shadow");
    expect(() =>
      parseShadowHttpResult({
        enabled: false,
        authority: "shadow",
        task: "general",
        local_model_id: "m1",
        nd_recommended_model_id: "nd-liar",
        agreement: null,
        notes: [],
      }),
    ).toThrow(/enabled=false/);
    expect(() =>
      parseShadowHttpResult({
        enabled: true,
        authority: "production",
        task: "t",
        local_model_id: "m1",
        nd_recommended_model_id: "m1",
        agreement: true,
        notes: [],
      }),
    ).toThrow(/shadow/);
  });
});

describe("postNotDiamondShadow", () => {
  it("POSTs shadow and parses body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        enabled: false,
        authority: "shadow",
        task: "general",
        local_model_id: "m1",
        nd_recommended_model_id: null,
        agreement: null,
        notes: ["kill_switch=off"],
      }),
      text: async () => "",
    } as unknown as Response);
    const body = await postNotDiamondShadow({
      local_model_id: "m1",
      nd_recommended_model_id: "would-discard",
    });
    expect(body.enabled).toBe(false);
    expect(body.nd_recommended_model_id).toBeNull();
    expect(mockFetch).toHaveBeenCalledWith(
      "/settings/notdiamond/shadow",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postNotDiamondShadow({ local_model_id: "m1" }),
    ).rejects.toBeInstanceOf(NotDiamondShadowHttpError);
  });
});
