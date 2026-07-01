import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attachBlock,
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
