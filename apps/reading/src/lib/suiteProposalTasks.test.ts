import { describe, expect, it } from "vitest";

import {
  groupProposedTasksByClass,
  primaryFeedSourceFromBySource,
  rankedFeedSourcesFromBySource,
  taskClassFromProposedItemId,
} from "./suiteProposalTasks";

describe("suiteProposalTasks residual (hg)", () => {
  it("parses usage-derived item ids into task classes", () => {
    expect(taskClassFromProposedItemId("usage-distill-abcd12-0")).toBe(
      "distill",
    );
    expect(taskClassFromProposedItemId("usage-wrestle-deadbeef-1")).toBe(
      "wrestle",
    );
    expect(taskClassFromProposedItemId("usage-book_qa-ffff-2")).toBe("book_qa");
  });

  it("returns null for empty or non-usage ids", () => {
    expect(taskClassFromProposedItemId("")).toBeNull();
    expect(taskClassFromProposedItemId("core-v1-item")).toBeNull();
  });

  it("groups proposed tasks by class", () => {
    const g = groupProposedTasksByClass([
      "usage-distill-a-0",
      "usage-distill-b-1",
      "usage-wrestle-c-0",
      "mystery-item",
    ]);
    expect(g.distill).toBe(2);
    expect(g.wrestle).toBe(1);
    expect(g.other).toBe(1);
  });
});

describe("suiteProposalTasks residual (qa / FUTURE-AGENT V3)", () => {
  it("picks primary by_source by max count (ties → name)", () => {
    expect(
      primaryFeedSourceFromBySource({
        twin_chase: 3,
        midnight_oil: 1,
        collective_merge: 2,
      }),
    ).toEqual({ source: "twin_chase", count: 3 });
    // Tie: lexicographic source wins.
    expect(
      primaryFeedSourceFromBySource({
        zebra: 2,
        alpha: 2,
      }),
    ).toEqual({ source: "alpha", count: 2 });
    expect(primaryFeedSourceFromBySource({})).toBeNull();
    expect(primaryFeedSourceFromBySource(null)).toBeNull();
  });

  it("ranks feed sources by count desc", () => {
    expect(
      rankedFeedSourcesFromBySource({
        twin_chase: 3,
        midnight_oil: 1,
        collective_merge: 2,
      }).map((x) => x.source),
    ).toEqual(["twin_chase", "collective_merge", "midnight_oil"]);
  });
});
