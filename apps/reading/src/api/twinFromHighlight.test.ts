import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  HighlightTwinHttpError,
  parseHighlightTwinSeed,
  postHighlightTwinSeed,
} from "./twinFromHighlight";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => mockFetch.mockReset());
afterEach(() => vi.restoreAllMocks());

const sample = {
  parent_asset_id: "asset-1",
  highlight: "A key sentence.",
  insights: ["insight"],
  questions: [],
  source_label: "highlight",
  notes: ["llm_filled=false"],
  llm_filled: false,
  authority: "highlight_seed_only",
};

describe("parseHighlightTwinSeed", () => {
  it("parses", () => {
    expect(parseHighlightTwinSeed(sample).highlight).toMatch(/key sentence/);
  });

  it("rejects llm_filled true", () => {
    expect(() =>
      parseHighlightTwinSeed({ ...sample, llm_filled: true }),
    ).toThrow(/llm_filled/);
  });
});

describe("postHighlightTwinSeed", () => {
  it("POSTs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const r = await postHighlightTwinSeed({
      parent_asset_id: "asset-1",
      highlight: "A key sentence.",
      insights: ["insight"],
    });
    expect(r.authority).toBe("highlight_seed_only");
  });

  it("rejects empty highlight without network", async () => {
    await expect(
      postHighlightTwinSeed({ parent_asset_id: "a", highlight: "  " }),
    ).rejects.toThrow(/highlight/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("rejects gated client-side without network", async () => {
    await expect(
      postHighlightTwinSeed({
        parent_asset_id: "a",
        highlight: "x",
        gated: true,
      }),
    ).rejects.toThrow(/gated/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postHighlightTwinSeed({ parent_asset_id: "a", highlight: "x" }),
    ).rejects.toBeInstanceOf(HighlightTwinHttpError);
  });
});
