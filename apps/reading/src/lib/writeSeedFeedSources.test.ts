import { describe, expect, it } from "vitest";
import {
  countWriteSeedKnownSources,
  isWriteSeedFeedSource,
  WRITE_SEED_FEED_SOURCES,
} from "./writeSeedFeedSources";

describe("writeSeedFeedSources (rt/ru)", () => {
  it("includes recursive note-taker Write seeds", () => {
    expect(WRITE_SEED_FEED_SOURCES).toContain("deep_research_session");
    expect(WRITE_SEED_FEED_SOURCES).toContain("research_progress_draft");
    expect(WRITE_SEED_FEED_SOURCES).toContain("twin_promote_context");
    // Residual (tt): multi-spawn cohesive unit prompt float.
    expect(WRITE_SEED_FEED_SOURCES).toContain("collective_unit_prompt");
    // Residual (vd): cross-asset twin merge Write seed.
    expect(WRITE_SEED_FEED_SOURCES).toContain("twin_cross_asset_merge");
    // Residual (vk): collective written analysis Write seed.
    expect(WRITE_SEED_FEED_SOURCES).toContain("collective_written_analysis");
    expect(WRITE_SEED_FEED_SOURCES).toContain("marketplace_catalog");
    expect(WRITE_SEED_FEED_SOURCES).not.toContain("twin_draft_selected");
  });

  it("classifies write seed sources honestly", () => {
    expect(isWriteSeedFeedSource("twin_promote_context")).toBe(true);
    expect(isWriteSeedFeedSource("twin_chase")).toBe(false);
    expect(isWriteSeedFeedSource("")).toBe(false);
    expect(isWriteSeedFeedSource(null)).toBe(false);
  });

  it("counts write-seed known sources (ru)", () => {
    expect(
      countWriteSeedKnownSources([
        "twin_chase",
        "twin_promote_context",
        "deep_research_session",
        "investigation_start",
      ]),
    ).toBe(2);
    expect(countWriteSeedKnownSources(["twin_chase"])).toBe(0);
    expect(countWriteSeedKnownSources(null)).toBe(0);
    expect(countWriteSeedKnownSources([])).toBe(0);
  });
});
