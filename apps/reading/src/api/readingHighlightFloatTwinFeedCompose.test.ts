import { describe, expect, it } from "vitest";
import {
  composeReadingHighlightFloatTwinFeed,
  formatReadingHighlightFloatTwinFeedSummary,
} from "./readingHighlightFloatTwinFeedCompose";

describe("composeReadingHighlightFloatTwinFeed", () => {
  it("spawn_only + twin feed ready", () => {
    const c = composeReadingHighlightFloatTwinFeed({
      session_id: "sess-1",
      parent_asset_id: "book-1",
      highlight: "scaling laws under noise",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_only",
      operator_ack: true,
      source_families: ["arxiv"],
      twin_findings: [
        {
          source_id: "extra-1",
          body: "claim A supported",
          kind: "insight",
        },
      ],
      mark_for_prompt_context: true,
    });
    expect(c.surface.surface_ready).toBe(true);
    expect(c.twin_feed?.feed_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.authority).toBe(
      "reading_highlight_float_twin_feed_compose_advisory",
    );
    expect(formatReadingHighlightFloatTwinFeedSummary(c)).toMatch(
      /twin_written=false/,
    );
  });

  it("gated highlight fails closed", () => {
    expect(() =>
      composeReadingHighlightFloatTwinFeed({
        session_id: "s",
        parent_asset_id: "b",
        highlight: "secret",
        gated: true,
        would_exceed: false,
        surface_action: "spawn_only",
        operator_ack: true,
      }),
    ).toThrow(/gated/);
  });

  it("skip twin still pack ready on surface", () => {
    const c = composeReadingHighlightFloatTwinFeed({
      session_id: "s",
      parent_asset_id: "b",
      highlight: "claim",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_only",
      operator_ack: true,
      include_twin_feed: false,
    });
    expect(c.twin_feed).toBeNull();
    expect(c.surface.surface_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
  });

  it("ack false not pack ready", () => {
    const c = composeReadingHighlightFloatTwinFeed({
      session_id: "s",
      parent_asset_id: "b",
      highlight: "claim",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_only",
      operator_ack: false,
    });
    expect(c.surface.surface_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("fullscreen surface + twin", () => {
    const c = composeReadingHighlightFloatTwinFeed({
      session_id: "s",
      parent_asset_id: "b",
      highlight: "claim A",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_and_fullscreen",
      operator_ack: true,
    });
    expect(c.surface.tray?.action).toBe("fullscreen_one");
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });
});
