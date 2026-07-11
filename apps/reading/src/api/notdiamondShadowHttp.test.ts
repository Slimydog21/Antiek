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
  it("POSTs shadow with enabled=false and strips ND reco", async () => {
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
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({
      task: "general",
      local_model_id: "m1",
      nd_recommended_model_id: null,
      enabled: false,
      extra_notes: [],
    });
  });

  it("rejects enabled=true without injected ND reco (no live ND)", async () => {
    await expect(
      postNotDiamondShadow({ local_model_id: "m1", enabled: true }),
    ).rejects.toThrow(/injected nd_recommended_model_id|no live ND/i);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("allows enabled=true only with explicit injected recommendation", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        enabled: true,
        authority: "shadow",
        task: "general",
        local_model_id: "m1",
        nd_recommended_model_id: "m2",
        agreement: false,
        notes: ["kill_switch=on"],
      }),
      text: async () => "",
    } as unknown as Response);
    const body = await postNotDiamondShadow({
      local_model_id: "m1",
      enabled: true,
      nd_recommended_model_id: "m2",
    });
    expect(body.agreement).toBe(false);
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body).enabled).toBe(true);
    expect(JSON.parse(init.body).nd_recommended_model_id).toBe("m2");
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
