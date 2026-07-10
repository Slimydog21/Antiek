import { describe, expect, it } from "vitest";

import {
  groupProposedTasksByClass,
  primaryFeedSourceFromBySource,
  rankedFeedSourcesFromBySource,
  taskClassFromProposedItemId,
  VISION_USAGE_FEED_SOURCES,
  visionFeedCoverageFromBySource,
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

describe("suiteProposalTasks residual (aoy) vision feed coverage", () => {
  it("ships a closed north-star vision feed source list", () => {
    expect(VISION_USAGE_FEED_SOURCES).toContain("twin_chase");
    expect(VISION_USAGE_FEED_SOURCES).toContain("floating_deep_research");
    expect(VISION_USAGE_FEED_SOURCES).toContain("midnight_oil");
    expect(VISION_USAGE_FEED_SOURCES).toContain("midnight_oil_deposit");
    expect(VISION_USAGE_FEED_SOURCES).toContain("collective_merge");
    expect(VISION_USAGE_FEED_SOURCES).toContain("book_qa");
    expect(VISION_USAGE_FEED_SOURCES.length).toBeGreaterThanOrEqual(6);
  });

  it("reports covered vs uncovered vision surfaces without inventing events", () => {
    const cov = visionFeedCoverageFromBySource({
      twin_chase: 3,
      midnight_oil: 1,
      other_noise: 99,
    });
    expect(cov.covered).toEqual(["twin_chase", "midnight_oil"]);
    expect(cov.uncovered).toContain("floating_deep_research");
    expect(cov.uncovered).toContain("collective_merge");
    expect(cov.uncovered).toContain("book_qa");
    expect(cov.covered_count).toBe(2);
    expect(cov.uncovered_count).toBe(cov.total - 2);
    expect(cov.covered_event_count).toBe(4);
    expect(cov.coverage_ratio).toBeCloseTo(2 / cov.total);
    // Zero / missing counts stay uncovered (never invent).
    expect(
      visionFeedCoverageFromBySource({ twin_chase: 0, book_qa: -1 }).covered,
    ).toEqual([]);
    expect(visionFeedCoverageFromBySource(null).covered_count).toBe(0);
    expect(visionFeedCoverageFromBySource({}).uncovered_count).toBe(
      VISION_USAGE_FEED_SOURCES.length,
    );
  });
});
