import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  TwinNotesHttpError,
  formatTwinSummary,
  getTwin,
  listTwinsForParent,
  mergeTwins,
  parseLines,
  parseListTwinsResult,
  parseTwinDocument,
  recordTwin,
} from "./twinNotes";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const sampleDoc = {
  twin_id: "twin-1",
  parent_asset_id: "asset-1",
  insights: ["insight A"],
  questions: ["q?"],
  source_label: "note-taker",
  created_at: 1,
  updated_at: 2,
  merged_from: [],
};

describe("formatters", () => {
  it("summary and line parse", () => {
    expect(formatTwinSummary(parseTwinDocument(sampleDoc))).toMatch(/twin-1/);
    expect(parseLines("a\n\nb\n  ")).toEqual(["a", "b"]);
  });
});

describe("parseTwinDocument", () => {
  it("requires twin_id and parent_asset_id", () => {
    expect(() =>
      parseTwinDocument({ ...sampleDoc, twin_id: "" }),
    ).toThrow(/twin_id/);
    expect(() =>
      parseTwinDocument({ ...sampleDoc, parent_asset_id: "" }),
    ).toThrow(/parent_asset_id/);
  });

  it("rejects missing/null lists, source_label, and non-finite timestamps", () => {
    expect(() =>
      parseTwinDocument({ ...sampleDoc, insights: null }),
    ).toThrow(/insights/);
    expect(() => {
      const { questions: _q, ...rest } = sampleDoc;
      parseTwinDocument(rest);
    }).toThrow(/questions/);
    expect(() =>
      parseTwinDocument({ ...sampleDoc, merged_from: undefined }),
    ).toThrow(/merged_from/);
    expect(() =>
      parseTwinDocument({ ...sampleDoc, source_label: null }),
    ).toThrow(/source_label/);
    expect(() =>
      parseTwinDocument({ ...sampleDoc, insights: [null] }),
    ).toThrow(/insights/);
    expect(() =>
      parseTwinDocument({ ...sampleDoc, created_at: Number.NaN }),
    ).toThrow(/created_at/);
    expect(() => {
      const { updated_at: _u, ...rest } = sampleDoc;
      parseTwinDocument(rest);
    }).toThrow(/updated_at/);
  });

  it("parses a valid document", () => {
    const d = parseTwinDocument(sampleDoc);
    expect(d.insights).toEqual(["insight A"]);
    expect(d.questions).toEqual(["q?"]);
  });
});

describe("parseListTwinsResult", () => {
  it("requires parent and twins array", () => {
    expect(() => parseListTwinsResult({ twins: [] })).toThrow(/parent_asset_id/);
    expect(() =>
      parseListTwinsResult({ parent_asset_id: "p", twins: "nope" }),
    ).toThrow(/twins/);
    const ok = parseListTwinsResult({
      parent_asset_id: "asset-1",
      twins: [sampleDoc],
    });
    expect(ok.twins).toHaveLength(1);
  });

  it("rejects envelope/child parent mismatches", () => {
    expect(() =>
      parseListTwinsResult(
        { parent_asset_id: "asset-B", twins: [sampleDoc] },
        "asset-1",
      ),
    ).toThrow(/mismatch/);
    expect(() =>
      parseListTwinsResult({
        parent_asset_id: "asset-1",
        twins: [{ ...sampleDoc, parent_asset_id: "other" }],
      }),
    ).toThrow(/parent/);
  });
});

describe("recordTwin", () => {
  it("POSTs and validates", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sampleDoc,
      text: async () => "",
    } as unknown as Response);
    const doc = await recordTwin({
      parent_asset_id: "asset-1",
      insights: ["insight A"],
      questions: ["q?"],
      source_label: "note-taker",
    });
    expect(doc.twin_id).toBe("twin-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/twins",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects empty parent without network", async () => {
    await expect(recordTwin({ parent_asset_id: "  " })).rejects.toThrow(
      /parent_asset_id/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("listTwinsForParent / getTwin / mergeTwins", () => {
  it("lists by parent", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ parent_asset_id: "asset-1", twins: [sampleDoc] }),
      text: async () => "",
    } as unknown as Response);
    const list = await listTwinsForParent("asset-1");
    expect(list.twins[0].twin_id).toBe("twin-1");
    expect(mockFetch.mock.calls[0][0]).toBe("/twins/by-parent/asset-1");
  });

  it("gets one twin", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sampleDoc,
      text: async () => "",
    } as unknown as Response);
    const doc = await getTwin("twin-1", "asset-1");
    expect(doc.parent_asset_id).toBe("asset-1");
    expect(String(mockFetch.mock.calls[0][0])).toContain(
      "/twins/twin-1?parent_asset_id=asset-1",
    );
  });

  it("merges and surfaces HTTP 409", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({
        detail: { code: "cross_parent_merge_rejected" },
      }),
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      mergeTwins({ twin_ids: ["a", "b"] }),
    ).rejects.toBeInstanceOf(TwinNotesHttpError);
  });

  it("rejects empty twin_ids for merge without network", async () => {
    await expect(mergeTwins({ twin_ids: [] })).rejects.toThrow(/twin_ids/);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
