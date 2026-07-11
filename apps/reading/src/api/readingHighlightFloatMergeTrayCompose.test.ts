import { describe, expect, it } from "vitest";
import {
  composeReadingHighlightFloatMergeTray,
  formatReadingHighlightFloatMergeTraySummary,
} from "./readingHighlightFloatMergeTrayCompose";

describe("composeReadingHighlightFloatMergeTray", () => {
  it("spawn_only ready without dispatch or merge", () => {
    const c = composeReadingHighlightFloatMergeTray({
      parent_asset_id: "book-1",
      highlight: "scaling laws under noise",
      gated: false,
      would_exceed: false,
      preferred_view_mode: "floating",
      source_families: ["arxiv"],
      surface_action: "spawn_only",
      operator_ack: true,
    });
    expect(c.surface_ready).toBe(true);
    expect(c.launch.launch_ready).toBe(true);
    expect(c.tray).toBeNull();
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.authority).toBe(
      "reading_highlight_float_merge_tray_compose_advisory",
    );
    expect(formatReadingHighlightFloatMergeTraySummary(c)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("spawn_and_fullscreen and draft_merge", () => {
    const fs = composeReadingHighlightFloatMergeTray({
      parent_asset_id: "book-1",
      highlight: "claim A",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_and_fullscreen",
      operator_ack: true,
    });
    expect(fs.surface_ready).toBe(true);
    expect(fs.tray?.action).toBe("fullscreen_one");
    expect(fs.tray?.pack_dispatched).toBe(false);

    const draft = composeReadingHighlightFloatMergeTray({
      parent_asset_id: "book-1",
      highlight: "claim B",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_and_draft_merge",
      operator_ack: true,
    });
    expect(draft.tray?.action).toBe("draft_merge_one");
    expect(draft.merge_executed).toBe(false);
  });

  it("spawn_and_full_merge not ready until completed (spawn is proposed)", () => {
    const c = composeReadingHighlightFloatMergeTray({
      parent_asset_id: "book-1",
      highlight: "claim C",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_and_full_merge",
      operator_ack: true,
    });
    // Spawned status is proposed — full merge requires completed
    expect(c.tray?.tray_ready).toBe(false);
    expect(c.surface_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("tray_collective with existing completed members", () => {
    const c = composeReadingHighlightFloatMergeTray({
      parent_asset_id: "book-1",
      highlight: "new highlight",
      gated: false,
      would_exceed: false,
      surface_action: "tray_collective",
      operator_ack: true,
      existing_members: [
        {
          instance_id: "existing-1",
          parent_asset_id: "book-1",
          status: "completed",
          live_dispatched: false,
          merge_executed: false,
        },
      ],
      selected_instance_ids: ["existing-1"],
    });
    expect(c.tray?.selected_count).toBeGreaterThanOrEqual(2);
    expect(c.tray?.action).toBe("collective_pack");
    expect(c.pack_dispatched).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("rejects gated highlights", () => {
    expect(() =>
      composeReadingHighlightFloatMergeTray({
        parent_asset_id: "book-1",
        highlight: "secret",
        gated: true,
        would_exceed: false,
        surface_action: "spawn_only",
        operator_ack: true,
      }),
    ).toThrow(/gated/);
  });
});
