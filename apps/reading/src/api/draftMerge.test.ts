import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  DraftMergeHttpError,
  formatProvisional,
  formatTwinCount,
  isCrossParentRejection,
  postDraftMerge,
} from "./draftMerge";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("honesty formatters", () => {
  it("provisional true is explicit not-merged language", () => {
    expect(formatProvisional(true)).toMatch(/PROVISIONAL/i);
    expect(formatProvisional(true)).toMatch(/not merged/i);
  });

  it("provisional null/undefined is unknown not false", () => {
    expect(formatProvisional(null)).toMatch(/unknown/i);
    expect(formatProvisional(undefined)).toMatch(/unknown/i);
  });

  it("twin count pluralizes", () => {
    expect(formatTwinCount([])).toBe("0 twins");
    expect(formatTwinCount(["a"])).toBe("1 twin");
    expect(formatTwinCount(["a", "b"])).toBe("2 twins");
  });
});

describe("postDraftMerge", () => {
  it("POSTs draft-merge and returns provisional body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        draft_id: "draft-abc",
        parent_asset_id: "parent-1",
        provisional: true,
        html: "<article data-provisional=\"true\">ok</article>",
        twin_ids: ["t1"],
        insight_count: 1,
        question_count: 0,
        created_at: 1,
        notes: [],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postDraftMerge({
      parent_asset_id: "parent-1",
      parent_html: "<p>src</p>",
      twin_ids: ["t1"],
      title: "Review draft",
    });

    expect(body.provisional).toBe(true);
    expect(body.draft_id).toBe("draft-abc");
    expect(mockFetch).toHaveBeenCalledWith(
      "/twins/draft-merge",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({
      parent_asset_id: "parent-1",
      parent_html: "<p>src</p>",
      twin_ids: ["t1"],
      title: "Review draft",
    });
  });

  it("rejects empty parent / empty twins without network", async () => {
    await expect(
      postDraftMerge({ parent_asset_id: "  ", twin_ids: ["t1"] }),
    ).rejects.toThrow(/parent_asset_id/);
    await expect(
      postDraftMerge({ parent_asset_id: "p", twin_ids: [] }),
    ).rejects.toThrow(/twin_ids/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces cross-parent 409 as DraftMergeHttpError", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({}),
      text: async () =>
        JSON.stringify({
          detail: {
            code: "cross_parent_draft_merge_rejected",
            message: "cross parent",
          },
        }),
    } as unknown as Response);

    try {
      await postDraftMerge({ parent_asset_id: "p", twin_ids: ["t1"] });
      expect.fail("expected throw");
    } catch (e) {
      expect(e).toBeInstanceOf(DraftMergeHttpError);
      expect(isCrossParentRejection(e)).toBe(true);
      expect((e as DraftMergeHttpError).code).toBe(
        "cross_parent_draft_merge_rejected",
      );
    }
  });
});
