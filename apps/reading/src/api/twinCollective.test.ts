import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  CollectivePackHttpError,
  formatPackPreview,
  formatParentIds,
  parseCollectivePackResult,
  postCollectivePack,
} from "./twinCollective";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("formatters", () => {
  it("parent ids and pack preview", () => {
    expect(formatParentIds([])).toMatch(/no parents/i);
    expect(formatParentIds(["a"])).toBe("1 parent: a");
    expect(formatParentIds(["a", "b"])).toBe("2 parents: a, b");
    expect(formatPackPreview("short")).toBe("short");
    expect(formatPackPreview("x".repeat(300)).endsWith("…")).toBe(true);
    expect(formatPackPreview("   ")).toBe("(empty pack)");
  });
});

describe("parseCollectivePackResult", () => {
  it("requires non-empty pack_text and twin_ids", () => {
    expect(() =>
      parseCollectivePackResult({ pack_text: "", twin_ids: ["t"] }),
    ).toThrow(/pack_text/);
    expect(() =>
      parseCollectivePackResult({ pack_text: "ok", twin_ids: [] }),
    ).toThrow(/twin_ids/);
    const ok = parseCollectivePackResult({
      instruction: "merge findings",
      twin_ids: ["t1", "t2"],
      parent_asset_ids: ["p1", "p2"],
      pack_text: "### Twin 1",
      insight_count: 2,
      question_count: 1,
      notes: ["cross-parent ok"],
    });
    expect(ok.pack_text).toMatch(/Twin 1/);
    expect(ok.parent_asset_ids).toEqual(["p1", "p2"]);
  });
});

describe("postCollectivePack", () => {
  it("POSTs collective and returns validated body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        instruction: "compare",
        twin_ids: ["t1"],
        parent_asset_ids: ["p1"],
        pack_text: "### Twin 1: t1\ninsights:\n- x",
        insight_count: 1,
        question_count: 0,
        notes: [],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postCollectivePack({
      twin_ids: ["t1"],
      instruction: "compare",
    });
    expect(body.pack_text).toMatch(/Twin 1/);
    expect(mockFetch).toHaveBeenCalledWith(
      "/twins/collective",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({
      twin_ids: ["t1"],
      instruction: "compare",
    });
  });

  it("rejects empty twin_ids without network", async () => {
    await expect(postCollectivePack({ twin_ids: [] })).rejects.toThrow(
      /twin_ids/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("rejects 200 with empty pack_text", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        twin_ids: ["t1"],
        pack_text: "   ",
        parent_asset_ids: [],
        insight_count: 0,
        question_count: 0,
        notes: [],
      }),
      text: async () => "",
    } as unknown as Response);
    await expect(
      postCollectivePack({ twin_ids: ["t1"] }),
    ).rejects.toThrow(/pack_text/);
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => "twin missing",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postCollectivePack({ twin_ids: ["missing"] }),
    ).rejects.toBeInstanceOf(CollectivePackHttpError);
  });
});
