import { describe, expect, it } from "vitest";
import {
  isWriteSeedFeedSource,
  WRITE_SEED_FEED_SOURCES,
} from "./writeSeedFeedSources";

describe("writeSeedFeedSources (rt)", () => {
  it("includes recursive note-taker Write seeds", () => {
    expect(WRITE_SEED_FEED_SOURCES).toContain("deep_research_session");
    expect(WRITE_SEED_FEED_SOURCES).toContain("research_progress_draft");
    expect(WRITE_SEED_FEED_SOURCES).toContain("twin_promote_context");
    expect(WRITE_SEED_FEED_SOURCES).not.toContain("twin_draft_selected");
  });

  it("classifies write seed sources honestly", () => {
    expect(isWriteSeedFeedSource("twin_promote_context")).toBe(true);
    expect(isWriteSeedFeedSource("twin_chase")).toBe(false);
    expect(isWriteSeedFeedSource("")).toBe(false);
    expect(isWriteSeedFeedSource(null)).toBe(false);
  });
});
