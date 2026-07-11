import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  NoteTakerHttpError,
  parseTwinNotePayload,
  postTwinNoteTakerPayload,
} from "./twinLlmNoteTaker";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => mockFetch.mockReset());
afterEach(() => vi.restoreAllMocks());

const sample = {
  parent_asset_id: "asset-1",
  insights: ["a"],
  questions: ["q?"],
  source_label: "llm-note-taker",
  llm_filled: true,
  asset_text_sha256: null,
  notes: ["model_invoked=false"],
  authority: "note_taker_payload_only",
  model_invoked: false,
};

describe("parseTwinNotePayload", () => {
  it("parses", () => {
    expect(parseTwinNotePayload(sample).insights).toEqual(["a"]);
  });

  it("rejects model_invoked true and empty lists", () => {
    expect(() =>
      parseTwinNotePayload({ ...sample, model_invoked: true }),
    ).toThrow(/model_invoked/);
    expect(() =>
      parseTwinNotePayload({ ...sample, insights: [], questions: [] }),
    ).toThrow(/insight or question/);
  });
});

describe("postTwinNoteTakerPayload", () => {
  it("POSTs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const r = await postTwinNoteTakerPayload({
      parent_asset_id: "asset-1",
      insights: ["a"],
      questions: ["q?"],
      llm_filled: true,
      gated: false,
    });
    expect(r.model_invoked).toBe(false);
  });

  it("rejects gated/empty without network", async () => {
    await expect(
      postTwinNoteTakerPayload({
        parent_asset_id: "a",
        insights: ["x"],
        llm_filled: true,
        gated: true,
      }),
    ).rejects.toThrow(/gated/);
    await expect(
      postTwinNoteTakerPayload({
        parent_asset_id: "a",
        insights: [],
        questions: [],
        llm_filled: false,
        gated: false,
      }),
    ).rejects.toThrow(/insight or question/);
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
      postTwinNoteTakerPayload({
        parent_asset_id: "a",
        insights: ["x"],
        llm_filled: true,
        gated: false,
      }),
    ).rejects.toBeInstanceOf(NoteTakerHttpError);
  });
});
