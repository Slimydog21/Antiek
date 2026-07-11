import { describe, expect, it } from "vitest";
import {
  composeHighlightDeepResearchLaunch,
  formatHighlightDeepResearchLaunchSummary,
} from "./highlightDeepResearchLaunchCompose";

describe("composeHighlightDeepResearchLaunch", () => {
  it("launches package from highlight without dispatch or merge", () => {
    const c = composeHighlightDeepResearchLaunch({
      parent_asset_id: "asset-read-1",
      highlight: "scaling laws under noise",
      gated: false,
      preferred_view_mode: "fullscreen",
      would_exceed: false,
      selected_model_id: "gpt-5",
      source_families: ["arxiv", "substack"],
      operator_ack: true,
    });
    expect(c.launch_ready).toBe(true);
    expect(c.preferred_view_mode).toBe("fullscreen");
    expect(c.instance.view_mode).toBe("fullscreen");
    expect(c.instance.live_dispatched).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.source_family_count).toBe(2);
    expect(c.budget_ready).toBe(true);
    expect(c.authority).toBe(
      "highlight_deep_research_launch_compose_advisory",
    );
    expect(formatHighlightDeepResearchLaunchSummary(c)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("budget unknown fails closed unless override", () => {
    const unk = composeHighlightDeepResearchLaunch({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
      would_exceed: null,
      operator_ack: true,
    });
    expect(unk.budget_ready).toBe(false);
    expect(unk.launch_ready).toBe(false);
    expect(unk.live_dispatched).toBe(false);

    const ov = composeHighlightDeepResearchLaunch({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
      would_exceed: null,
      operator_override: true,
      operator_ack: true,
    });
    expect(ov.budget_ready).toBe(true);
    expect(ov.launch_ready).toBe(true);
    expect(ov.live_dispatched).toBe(false);
  });

  it("rejects gated highlights and secret-like model ids", () => {
    expect(() =>
      composeHighlightDeepResearchLaunch({
        parent_asset_id: "a",
        highlight: "h",
        gated: true,
        would_exceed: false,
        operator_ack: true,
      }),
    ).toThrow(/gated/);
    expect(() =>
      composeHighlightDeepResearchLaunch({
        parent_asset_id: "a",
        highlight: "h",
        gated: false,
        would_exceed: false,
        selected_model_id: "sk-secretkey",
        operator_ack: true,
      }),
    ).toThrow(/secret|model id/i);
  });

  it("not ready without operator_ack", () => {
    const c = composeHighlightDeepResearchLaunch({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.launch_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
  });
});
