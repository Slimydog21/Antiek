import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attachBlock,
  appendNotebookBlock,
  getNotebook,
  getTrajectory,
  listInvestigations,
  listWatchForLater,
  reorderBlock,
  searchBlocks,
} from "./api";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client numeric request bounds", () => {
  it("rejects malformed list/search limits before sending requests", async () => {
    await expect(getTrajectory("inv-1", 0)).rejects.toThrow(/limit/);
    await expect(listInvestigations({ limit: -1 })).rejects.toThrow(/limit/);
    await expect(listWatchForLater({ limit: 2.5 })).rejects.toThrow(/limit/);
    await expect(searchBlocks("claim", 9007199254740992)).rejects.toThrow(/limit/);

    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects malformed section block indices before sending requests", async () => {
    await expect(
      attachBlock({
        section_id: "sec-1",
        block_kind: "claim",
        block_id: "blk-1",
        block_index: -1,
      }),
    ).rejects.toThrow(/block_index/);
    await expect(
      reorderBlock({
        section_id: "sec-1",
        block_kind: "claim",
        block_id: "blk-1",
        new_block_index: 1.5,
      }),
    ).rejects.toThrow(/new_block_index/);

    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("api client notebook response boundary", () => {
  it("sanitizes notebook responses before rendering blocks", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          notebook_id: " nb-1 ",
          title: " ",
          investigation_id: " inv-1 ",
          document_id: " ",
          content_class: "surprise",
          created_at: " 2026-07-01T00:00:00Z ",
          updated_at: " ",
          blocks: [
            {
              block_id: " blk-1 ",
              block_index: 0,
              block_type: " prose ",
              ref_id: " ",
              content_json: { text: "Hello" },
              created_at: " 2026-07-01T00:01:00Z ",
            },
            {
              block_id: "blk-bad-type",
              block_index: 1,
              block_type: "unknown",
              content_json: { text: "Skip" },
            },
            {
              block_id: "",
              block_index: 2,
              block_type: "note",
              content_json: { text: "Skip" },
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getNotebook("nb-1")).resolves.toEqual({
      notebook_id: "nb-1",
      title: "nb-1",
      investigation_id: "inv-1",
      document_id: null,
      content_class: "user_owned",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "",
      blocks: [
        {
          block_id: "blk-1",
          block_index: 0,
          block_type: "prose",
          ref_id: null,
          content_json: { text: "Hello" },
          created_at: "2026-07-01T00:01:00Z",
        },
      ],
    });
  });

  it("rejects notebook responses without a usable notebook id", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ notebook_id: " ", blocks: [] }), {
        status: 200,
      }),
    );

    await expect(getNotebook("nb-1")).rejects.toMatchObject({ status: 502 });
  });

  it("sanitizes append notebook responses through the same boundary", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          notebook_id: " nb-append ",
          title: "Append",
          content_class: "user_public_contribution",
          blocks: [
            {
              block_id: " block-1 ",
              block_index: 0,
              block_type: "note",
              ref_id: " note-1 ",
              content_json: [],
              created_at: null,
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const result = await appendNotebookBlock("nb-append", {
      block_type: "note",
      content: { text: "x" },
    });

    expect(result.notebook_id).toBe("nb-append");
    expect(result.content_class).toBe("user_public_contribution");
    expect(result.blocks).toEqual([
      {
        block_id: "block-1",
        block_index: 0,
        block_type: "note",
        ref_id: "note-1",
        content_json: {},
        created_at: "",
      },
    ]);
  });
});
